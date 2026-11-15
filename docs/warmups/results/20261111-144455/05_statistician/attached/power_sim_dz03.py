"""2x2 피험자내 설계, 주효과 A 하나에 대한 검정력 시뮬레이션.

가정
- 주효과 A 검정 = 참가자별 [mean(A1B1, A1B2) - mean(A2B1, A2B2)] 차이점수의 일표본 t 검정
  (= 대응 t 검정 = 2x2 RM-ANOVA 의 A 주효과 F(1, N-1) 와 동치, F = t^2).
- 차이점수 ~ Normal(dz, 1)  -> 표준화 효과 dz = mean(diff)/sd(diff) = 0.3.
- 양측 alpha = .05, 목표 검정력 .80.
- 검산 1: 비중심 t 분포 해석해.
- 검산 2: 4개 셀 수준 생성(복합대칭, 셀 SD=1, 셀 간 상관 rho)에서 A 주효과를 계산.
  Var(diff) = 1 - rho 이므로 평균 이동 = dz * sqrt(1 - rho) 로 두면 dz 가 동일하다.
  B 주효과·AxB 상호작용은 0 으로 둔다(A 검정에는 영향 없음).
"""
import sys
import numpy as np
import pandas as pd
from scipy import stats

SEED = 20261111
DZ = 0.3
ALPHA = 0.05
TARGET = 0.80
NSIM = 20000          # 각 N 당 반복 수
N_GRID = range(70, 111)
RHO_CHECK = [0.3, 0.5, 0.7]
NSIM_CHECK = 20000

rng = np.random.default_rng(SEED)


def sim_power_diff(n, nsim):
    d = rng.normal(DZ, 1.0, size=(nsim, n))
    t = d.mean(1) / (d.std(1, ddof=1) / np.sqrt(n))
    p = 2 * stats.t.sf(np.abs(t), df=n - 1)
    return (p < ALPHA).mean()


def analytic_power(n):
    df = n - 1
    nc = DZ * np.sqrt(n)
    tc = stats.t.ppf(1 - ALPHA / 2, df)
    return stats.nct.sf(tc, df, nc) + stats.nct.cdf(-tc, df, nc)


def sim_power_cells(n, nsim, rho):
    cov = np.full((4, 4), rho) + np.eye(4) * (1 - rho)
    shift = DZ * np.sqrt(1 - rho)
    mu = np.array([shift / 2, shift / 2, -shift / 2, -shift / 2])  # A1B1 A1B2 A2B1 A2B2
    y = rng.multivariate_normal(mu, cov, size=(nsim, n))
    diff = y[..., :2].mean(-1) - y[..., 2:].mean(-1)
    t = diff.mean(1) / (diff.std(1, ddof=1) / np.sqrt(n))
    p = 2 * stats.t.sf(np.abs(t), df=n - 1)
    return (p < ALPHA).mean()


rows = []
for n in N_GRID:
    pw = sim_power_diff(n, NSIM)
    se = np.sqrt(pw * (1 - pw) / NSIM)
    rows.append(dict(N=n, power_sim=pw, mc_se=se,
                     ci95_lo=pw - 1.96 * se, ci95_hi=pw + 1.96 * se,
                     power_analytic=analytic_power(n)))
df = pd.DataFrame(rows)
df.to_csv("power_curve_dz03.csv", index=False)

n_sim = int(df.loc[df.power_sim >= TARGET, "N"].min())
n_ana = int(df.loc[df.power_analytic >= TARGET, "N"].min())
# 몬테카를로 오차를 고려한 보수적 기준: 95% CI 하한이 .80 이상이 되는 최소 N
n_cons = df.loc[df.ci95_lo >= TARGET, "N"]
n_cons = int(n_cons.min()) if len(n_cons) else None

print(f"python {sys.version.split()[0]}, numpy {np.__version__}, scipy {stats.__name__ and __import__('scipy').__version__}, pandas {pd.__version__}")
print(f"seed={SEED}, nsim/N={NSIM}, dz={DZ}, alpha={ALPHA} (two-sided)")
print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
print(f"\n[결과] 시뮬레이션 검정력 >= .80 최소 N = {n_sim}")
print(f"[결과] 해석해(비중심 t) >= .80 최소 N = {n_ana}")
print(f"[결과] 시뮬레이션 95% CI 하한 >= .80 최소 N = {n_cons}")

print("\n[검산] 셀 수준(2x2, 복합대칭) 생성")
chk = []
for rho in RHO_CHECK:
    for n in sorted({n_ana - 5, n_ana, n_ana + 5}):
        pw = sim_power_cells(n, NSIM_CHECK, rho)
        chk.append(dict(rho=rho, N=n, power_cells=pw,
                        mc_se=np.sqrt(pw * (1 - pw) / NSIM_CHECK),
                        power_analytic=analytic_power(n)))
chk = pd.DataFrame(chk)
chk.to_csv("power_cells_check.csv", index=False)
print(chk.to_string(index=False, float_format=lambda x: f"{x:.4f}"))
