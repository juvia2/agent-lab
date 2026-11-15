#!/usr/bin/env python3
"""report.md 수치 재계산 스크립트 (QA Verifier).
사용: python3 review/recompute.py inputs/raw_rt.csv
시드: 부트스트랩 seed=20261111, 10000회.
"""
import sys, csv, math, random, json
from collections import defaultdict

path = sys.argv[1] if len(sys.argv) > 1 else 'inputs/raw_rt.csv'
rows = []
with open(path, newline='', encoding='utf-8-sig') as f:
    for r in csv.DictReader(f):
        rows.append(r)

out = {}
# ---- 1. 자료 구조 ----
bad = []
data = []
for i, r in enumerate(rows):
    try:
        data.append((r['subject'].strip(), r['condition'].strip(), r['item'].strip(), float(r['rt_ms'])))
    except Exception as e:
        bad.append((i, r, str(e)))
subs = sorted({d[0] for d in data})
conds = sorted({d[1] for d in data})
out['n_rows'] = len(rows)
out['n_unparsable'] = len(bad)
out['n_subjects'] = len(subs)
out['conditions'] = conds
cell = defaultdict(list)
keycount = defaultdict(int)
for s, c, it, rt in data:
    cell[(s, c)].append(rt)
    keycount[(s, c, it)] += 1
out['n_duplicate_keys'] = sum(1 for v in keycount.values() if v > 1)
per_cell_n = sorted({len(v) for v in cell.values()})
out['trials_per_subject_condition'] = per_cell_n
items_by_cond = {c: sorted({d[2] for d in data if d[1] == c}, key=lambda x: (len(x), x)) for c in conds}
out['n_items_per_condition'] = {c: len(v) for c, v in items_by_cond.items()}
missing_cells = [(s, c) for s in subs for c in conds if (s, c) not in cell]
out['missing_subject_condition_cells'] = missing_cells

# ---- 2. RT 분포 / 절단 ----
rts = [d[3] for d in data]
out['rt_min'] = min(rts); out['rt_max'] = max(rts)
out['n_rt_eq_min'] = sum(1 for x in rts if x == min(rts))
out['n_rt_eq_min_by_cond'] = {c: sum(1 for d in data if d[1] == c and d[3] == min(rts)) for c in conds}
out['n_rt_lt_200'] = sum(1 for x in rts if x < 200)
out['n_rt_gt_2000'] = sum(1 for x in rts if x > 2000)

def mean(x): return sum(x) / len(x)
def sd(x):
    m = mean(x); return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))

# ---- 3. 조건 평균 ----
out['trial_mean'] = {c: round(mean([d[3] for d in data if d[1] == c]), 3) for c in conds}
subj_mean = {(s, c): mean(v) for (s, c), v in cell.items()}
out['mean_of_subject_means'] = {c: round(mean([subj_mean[(s, c)] for s in subs if (s, c) in subj_mean]), 3) for c in conds}

# ---- 4. 대응표본 t (참가자 평균) ----
A, B = 'A', 'B'
paired = [s for s in subs if (s, A) in subj_mean and (s, B) in subj_mean]
diffs = [subj_mean[(s, B)] - subj_mean[(s, A)] for s in paired]
n = len(diffs)
md, sdd = mean(diffs), sd(diffs)
t = md / (sdd / math.sqrt(n))
out['paired_n'] = n
out['diff_B_minus_A'] = round(md, 3)
out['sd_diff'] = round(sdd, 3)
out['t'] = round(t, 3)
out['df'] = n - 1
out['cohen_dz'] = round(md / sdd, 3)
try:
    from scipy import stats
    out['p_two_sided'] = float(stats.ttest_rel([subj_mean[(s, B)] for s in paired], [subj_mean[(s, A)] for s in paired]).pvalue)
    tc = stats.t.ppf(0.975, n - 1)
    out['ci95_t'] = [round(md - tc * sdd / math.sqrt(n), 3), round(md + tc * sdd / math.sqrt(n), 3)]
    out['wilcoxon_p'] = float(stats.wilcoxon(diffs).pvalue)
except Exception as e:
    out['scipy_error'] = str(e)

rng = random.Random(20261111)
boots = []
for _ in range(10000):
    smp = [diffs[rng.randrange(n)] for _ in range(n)]
    boots.append(mean(smp))
boots.sort()
out['boot_ci95_subjects'] = [round(boots[249], 3), round(boots[9749], 3)]

out['n_subjects_B_slower'] = sum(1 for d in diffs if d > 0)
out['n_subjects_B_faster_or_equal'] = sum(1 for d in diffs if d <= 0)
out['subjects_B_not_slower'] = [s for s, d in zip(paired, diffs) if d <= 0]
out['per_subject_diff'] = {s: round(d, 2) for s, d in zip(paired, diffs)}

# ---- 5. 문항 단위 (탐색적) ----
item_cell = defaultdict(list)
for s, c, it, rt in data:
    item_cell[(it, c)].append(rt)
common_items = sorted({it for (it, c) in item_cell if (it, A) in item_cell and (it, B) in item_cell}, key=lambda x: (len(x), x))
idiffs = [mean(item_cell[(it, B)]) - mean(item_cell[(it, A)]) for it in common_items]
if len(idiffs) > 1:
    out['by_item_n'] = len(idiffs)
    out['by_item_diff'] = round(mean(idiffs), 3)
    out['by_item_t'] = round(mean(idiffs) / (sd(idiffs) / math.sqrt(len(idiffs))), 3)
    out['n_items_B_slower'] = sum(1 for d in idiffs if d > 0)

# ---- 6. 혼합효과모형 (탐색적, 가능할 때) ----
try:
    import pandas as pd
    import statsmodels.formula.api as smf
    df = pd.DataFrame(data, columns=['subject', 'condition', 'item', 'rt'])
    df['cB'] = (df['condition'] == B).astype(float) - 0.5
    df['grp'] = 1
    md_ = smf.mixedlm('rt ~ cB', df, groups='grp', re_formula='0',
                      vc_formula={'subject': '0 + C(subject)', 'item': '0 + C(item)'}).fit(reml=True)
    out['mixed_cB_coef'] = round(float(md_.params['cB']), 3)
    out['mixed_cB_se'] = round(float(md_.bse['cB']), 3)
    out['mixed_cB_z'] = round(float(md_.tvalues['cB']), 3)
    out['mixed_note'] = 'subject, item 무선절편 교차 (기울기 없음)'
except Exception as e:
    out['mixed_error'] = str(e)[:200]

print(json.dumps(out, ensure_ascii=False, indent=1))
with open('review/recompute_output.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
