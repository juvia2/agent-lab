## 1) 사전 추정 (계산값이며 실측 아님)

**공통 가정**
- 문장 1,000개 × 20토큰 ≈ **2만 토큰**. 문장당 forward 1회(teacher forcing)로 계산하고, 생성은 하지 않는다.
- 연산량은 토큰당 약 2N FLOPs(N = 파라미터 수, 출력 헤드 포함)로 잡는다.
- 맥북 CPU에서 PyTorch fp32의 실효 처리량은 50–300 GFLOPS로 넓게 가정한다. 칩 세대, 배치 크기, 스레드 수에 따라 크게 달라지는 값이고, 짧은 시퀀스에서는 효율이 낮다.
- 메모리 = 가중치(fp32 4B/param) + 로딩 피크 + logits(배치×길이×어휘×4B, log_softmax 사본 포함) + Python/torch 기본 약 0.5GB.

| 모델 | 총 연산량 | 추론 시간 (2만 토큰) | 모델 로딩 | 가중치 (fp32) | 예상 피크 RSS |
|---|---|---|---|---|---|
| ~1억 | 4×10¹² | 약 15초–1.5분 | 수 초 | 0.4 GB | 1–1.5 GB |
| ~3억 | 1.2×10¹³ | 약 40초–4분 | 5–15초 | 1.2 GB | 2–3 GB |
| ~8억 | 3.2×10¹³ | 약 2–11분 | 10–30초 | 3.2 GB | 4.5–7 GB |

- 세 모델을 모두 돌려도 최악의 경우 20분 이내로 예상한다. 이 규모라면 CPU로 충분하고 GPU(MPS)는 필요 없어 보인다.
- **메모리 변수는 어휘 크기다.** 다국어 모델(어휘 25만 안팎)은 배치 32에서 logits만 0.7–1.5 GB가 된다. 메모리가 빠듯하면 배치를 8–16으로 줄인다.
- **bf16은 권장하지 않는다.** 메모리는 절반이 되지만 맥 CPU에서는 오히려 느릴 수 있고, surprisal 정밀도도 떨어진다.
- **토큰 수가 모델마다 다를 수 있다.** 한국어에서는 토크나이저에 따라 같은 문장이 15토큰이 되기도 하고 40토큰이 되기도 한다. "평균 20토큰"이 어느 토크나이저 기준인지 확인이 필요하다. 벤치마크 스크립트가 모델별 실제 총 토큰 수를 세어 소요 시간을 다시 계산한다.

## 2) 5분 벤치마크 절차

**준비 (시간 측정 제외)**
- 세 모델은 미리 로컬에 받아 둔다.
- 전원 어댑터를 연결하고 다른 무거운 앱은 닫는다(발열·저전력 모드로 속도가 떨어지는 것을 막기 위해).
- 문장 파일은 한 줄에 한 문장.

**실행 (모델당 1–1.5분, 별도 프로세스로 3회)**
```bash
for m in /path/model_100m /path/model_300m /path/model_800m; do
  python bench_surprisal.py "$m" sentences.txt 64 | tee -a bench.jsonl
done
```

```python
# bench_surprisal.py  MODEL_PATH SENT_FILE [N_SAMPLE=64]
import sys, time, json, math, random, resource, platform
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

path, sfile = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 64
random.seed(0); torch.manual_seed(0)

sents = [l.strip() for l in open(sfile, encoding="utf-8") if l.strip()]
t0 = time.perf_counter()
tok = AutoTokenizer.from_pretrained(path)
model = AutoModelForCausalLM.from_pretrained(
    path, torch_dtype=torch.float32, low_cpu_mem_usage=True).eval()
load_s = time.perf_counter() - t0
n_params = sum(p.numel() for p in model.parameters())
start_id = tok.bos_token_id if tok.bos_token_id is not None else tok.eos_token_id
pad_id = tok.pad_token_id if tok.pad_token_id is not None else start_id

# 첫 토큰 surprisal을 위해 BOS(없으면 EOS)를 앞에 붙임
ids_all = [[start_id] + tok(s, add_special_tokens=False).input_ids for s in sents]
total_tgt = sum(len(x) - 1 for x in ids_all)          # 전체 1,000문장 실제 토큰 수
sample = sorted(random.sample(ids_all, min(n, len(ids_all))), key=len)

def score(batch):
    L = max(map(len, batch))
    inp = torch.full((len(batch), L), pad_id); att = torch.zeros_like(inp)
    for i, x in enumerate(batch):
        inp[i, :len(x)] = torch.tensor(x); att[i, :len(x)] = 1
    with torch.inference_mode():
        logp = torch.log_softmax(
            model(input_ids=inp, attention_mask=att).logits[:, :-1].float(), -1)
    s = -logp.gather(-1, inp[:, 1:, None]).squeeze(-1) / math.log(2)   # bits
    return [s[i, :len(x) - 1] for i, x in enumerate(batch)]

score(sample[:4])  # warm-up
ntok = sum(len(x) - 1 for x in sample)
res = {}
for bs in (1, 16):
    t = time.perf_counter(); out = []
    for i in range(0, len(sample), bs):
        out += score(sample[i:i + bs])
    dt = time.perf_counter() - t
    res[bs] = {"sec": dt, "tok_per_s": ntok / dt, "out": out}

maxdiff = max((a - b).abs().max().item()
              for a, b in zip(res[1]["out"], res[16]["out"]))
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
rss_gb = rss / 1e9 if platform.system() == "Darwin" else rss / 1e6
best = max(res[1]["tok_per_s"], res[16]["tok_per_s"])
print(json.dumps({
    "model": path, "n_params_M": round(n_params / 1e6, 1),
    "threads": torch.get_num_threads(), "torch": torch.__version__,
    "load_s": round(load_s, 1), "mean_tok_per_sent": round(total_tgt / len(sents), 1),
    "tok_per_s_bs1": round(res[1]["tok_per_s"], 1),
    "tok_per_s_bs16": round(res[16]["tok_per_s"], 1),
    "bs1_vs_bs16_maxdiff_bits": maxdiff,
    "peak_rss_GB": round(rss_gb, 2),
    "projected_full_run_s": round(load_s + total_tgt / best, 1)}, ensure_ascii=False))
```

**결과 판독**
1. **전체 소요 시간:** `projected_full_run_s`를 위 표의 범위와 비교한다. 64문장으로 외삽한 값이므로 ±20% 정도의 오차는 감안한다.
2. **메모리:** `peak_rss_GB`가 실제 피크다. 맥 물리 메모리의 60%를 넘으면 배치를 줄이거나 모델을 하나씩 순차 실행한다.
3. **정합성 점검:** `bs1_vs_bs16_maxdiff_bits`가 1e-3 이하여야 한다. 이보다 크면 패딩 또는 어텐션 마스크 처리에 문제가 있으므로 배치 결과를 쓰지 않는다.
4. **토큰 수:** `mean_tok_per_sent`가 모델마다 크게 다르면 토크나이저 교란이 있다는 뜻이다. 본 분석에서 단어(어절) 단위로 surprisal을 합산할지는 @Linguist 와 논의가 필요하다.

**참고 사항**
- 이 수치는 실측하지 않았다. 샌드박스는 리눅스 도커 CPU라 맥북 성능을 대표하지 못하고, 모델도 없어서 돌리지 않았다.
- 메인 실험으로 진행한다면 연구실 규칙상 "호스트(맥) 직접 실행"과 "모델 다운로드"를 계획 단계에서 미리 선언하고 승인받아야 한다. `run_manifest.json`에는 모델 리비전(커밋 해시), 스레드 수, torch·transformers 버전을 기록한다.
