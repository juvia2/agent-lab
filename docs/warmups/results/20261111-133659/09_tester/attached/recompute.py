"""보고서(inputs/report.md) 수치 재계산 스크립트.
사용법: python -I review/recompute.py inputs/raw_rt.csv review/recompute_results.json
표준 라이브러리만 사용한다(scipy가 있으면 p값도 계산한다). 부트스트랩 시드는 20261111로 고정했다.
"""
import csv, sys, json, math, random, statistics as st
from collections import defaultdict, Counter

path = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else None
rows, bad = [], []
with open(path, newline='', encoding='utf-8') as f:
    for i, r in enumerate(csv.DictReader(f), start=2):
        try:
            v = float(r['rt_ms'])
            if math.isnan(v):
                raise ValueError
            rows.append((r['subject'].strip(), r['condition'].strip(), r['item'].strip(), v))
        except Exception:
            bad.append((i, r))

res = {}
res['n_rows_valid'] = len(rows)
res['n_rows_bad_or_missing'] = len(bad)
res['bad_rows_sample'] = [str(b) for b in bad[:5]]
subs = sorted({r[0] for r in rows}); conds = sorted({r[1] for r in rows})
res['n_subjects'] = len(subs); res['conditions'] = conds
items_by_cond = defaultdict(set)
for s, c, it, v in rows:
    items_by_cond[c].add(it)
res['n_items_per_condition'] = {c: len(items_by_cond[c]) for c in conds}
cnt = Counter((s, c, it) for s, c, it, v in rows)
res['n_duplicate_cells'] = sum(1 for k, n in cnt.items() if n > 1)
cell = Counter((s, c) for s, c, it, v in rows)
res['trials_per_subject_condition_minmax'] = [min(cell.values()), max(cell.values())]
res['item_overlap_between_conditions'] = len(set.intersection(*items_by_cond.values())) if len(conds) > 1 else None
all_rt = [r[3] for r in rows]
res['rt_min_max'] = [min(all_rt), max(all_rt)]
res['n_rt_le_0'] = sum(v <= 0 for v in all_rt)

# 조건 평균 (시행 단위, 참가자 평균의 평균)
res['trial_mean_by_cond'] = {c: st.mean([v for s, cc, it, v in rows if cc == c]) for c in conds}
sm = defaultdict(list)
for s, c, it, v in rows:
    sm[(s, c)].append(v)
submean = {k: st.mean(v) for k, v in sm.items()}
res['mean_of_subject_means_by_cond'] = {c: st.mean([submean[(s, c)] for s in subs if (s, c) in submean]) for c in conds}

# 대응표본 t (B - A)
A, B = 'A', 'B'
paired = [s for s in subs if (s, A) in submean and (s, B) in submean]
d = [submean[(s, B)] - submean[(s, A)] for s in paired]
n = len(d); md = st.mean(d); sd = st.stdev(d); se = sd / math.sqrt(n); t = md / se
res['paired'] = {'n': n, 'df': n - 1, 'mean_diff_B_minus_A': md, 'sd_diff': sd, 't': t, 'cohens_dz': md / sd}
try:
    from scipy import stats
    res['paired']['p_two_sided'] = float(stats.ttest_rel([submean[(s, B)] for s in paired], [submean[(s, A)] for s in paired]).pvalue)
    tc = stats.t.ppf(0.975, n - 1)
    res['paired']['t_ci95'] = [md - tc * se, md + tc * se]
except Exception as e:
    res['paired']['p_two_sided'] = 'scipy 없음: ' + str(e)
res['n_subjects_B_slower'] = sum(x > 0 for x in d)
res['n_subjects_B_faster_or_equal'] = sum(x <= 0 for x in d)
res['subject_diffs'] = {s: round(x, 2) for s, x in zip(paired, d)}

# 참가자 부트스트랩 CI
rng = random.Random(20261111)
boots = sorted(st.mean(rng.choices(d, k=n)) for _ in range(10000))
res['bootstrap_subject_ci95'] = [boots[249], boots[9749]]

# 항목 단위 분석(문항 간 변동 점검; 문항이 조건 간 같으면 대응, 다르면 독립 비교)
im = defaultdict(list)
for s, c, it, v in rows:
    im[(it, c)].append(v)
itmean = {k: st.mean(v) for k, v in im.items()}
ia = [itmean[(it, A)] for it in sorted(items_by_cond[A], key=lambda x: int(x) if x.isdigit() else x)]
ib = [itmean[(it, B)] for it in sorted(items_by_cond[B], key=lambda x: int(x) if x.isdigit() else x)]
welch_se = math.sqrt(st.variance(ia) / len(ia) + st.variance(ib) / len(ib))
res['by_item'] = {'mean_A': st.mean(ia), 'mean_B': st.mean(ib), 'diff': st.mean(ib) - st.mean(ia), 'welch_t': (st.mean(ib) - st.mean(ia)) / welch_se}

# 보고서 수치 대조
rep = {'n_subjects': 24, 'items_per_cond': 20, 'n_trials': 960, 'mean_A': 402.7, 'mean_B': 460.0, 'diff': 39.4, 't': 3.44, 'df': 23, 'n_B_slower': 24}
cmp = []
def chk(name, reported, value, tol):
    cmp.append({'item': name, 'reported': reported, 'recomputed': round(value, 3) if isinstance(value, float) else value, 'match': abs(value - reported) <= tol})
chk('참가자 수', rep['n_subjects'], res['n_subjects'], 0)
chk('조건 A 문항 수', rep['items_per_cond'], res['n_items_per_condition'].get(A, -1), 0)
chk('조건 B 문항 수', rep['items_per_cond'], res['n_items_per_condition'].get(B, -1), 0)
chk('총 시행 수', rep['n_trials'], res['n_rows_valid'], 0)
chk('조건 A 평균(참가자 평균의 평균)', rep['mean_A'], res['mean_of_subject_means_by_cond'][A], 0.05)
chk('조건 B 평균(참가자 평균의 평균)', rep['mean_B'], res['mean_of_subject_means_by_cond'][B], 0.05)
chk('차이 B-A', rep['diff'], md, 0.05)
chk('t', rep['t'], t, 0.005)
chk('df', rep['df'], n - 1, 0)
chk('B가 더 느린 참가자 수', rep['n_B_slower'], res['n_subjects_B_slower'], 0)
chk('보고서 내부: 460.0-402.7 vs 39.4', rep['diff'], rep['mean_B'] - rep['mean_A'], 0.05)
res['comparison'] = cmp

txt = json.dumps(res, ensure_ascii=False, indent=1)
print(txt)
if out:
    open(out, 'w', encoding='utf-8').write(txt)
