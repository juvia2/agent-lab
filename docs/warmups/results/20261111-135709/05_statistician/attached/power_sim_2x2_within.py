"""2x2 피험자내 설계, 주효과 A 하나에 대한 검정력 시뮬레이션.

가정
- 각 참가자가 4개 셀(A1B1, A1B2, A2B1, A2B2)을 모두 경험한다.
- 셀 점수는 다변량정규, 셀 분산 1, 셀 간 상관 rho(복합대칭).
- 주효과 A의 참가자별 대비: D_i = mean(A2B1, A2B2) - mean(A1B1, A1B2).
- 효과크기 dz = mean(D) / sd(D) = 0.3 이 되도록 A의 셀 평균 차이를 맞춘다.
- B 주효과와 AxB 상호작용은 0 (dz 정의상 검정력에 영향 없음).
- 검정: D_i 에 대한 일표본 t 검정(양측, alpha=.05).
  RM-ANOVA 의 A 주효과 F(1, n-1) 와 동일(F = t^2).
- 셀 간 상관 rho 는 dz 를 고정하면 검정력에 영향이 없다(확인용으로 2개 값 실행).
"""
import sys
import numpy as np
from scipy import stats

DZ = 0.3
ALPHA = 0.05
TARGET = 0.80
REPS = 20000
SEED = 20261111
N_GRID = list(range(70, 111, 2))


def analytic_power(n, dz=DZ, alpha=ALPHA):
    df = n - 1
    nc = dz * np.sqrt(n)
    tcrit = stats.t.ppf(1 - alpha / 2, df)
    return (1 - stats.nct.cdf(tcrit, df, nc)) + stats.nct.cdf(-tcrit, df, nc)


def simulate(n, rho, rng, reps=REPS):
    # 복합대칭 공분산(분산 1)
    cov = np.full((4, 4), rho) + np.eye(4) * (1 - rho)
    # 대비 벡터 c: D = c @ y
    c = np.array([-0.5, -0.5, 0.5, 0.5])
    sd_D = np.sqrt(c @ cov @ c)  # = sqrt(1-rho)
    delta = DZ * sd_D            # 원하는 mean(D)
    # A2 셀에 +delta/2, A1 셀에 -delta/2  -> mean(D) = delta
    mu = np.array([-delta / 2, -delta / 2, delta / 2, delta / 2])
    L = np.linalg.cholesky(cov)
    z = rng.standard_normal((reps, n, 4))
    y = mu + z @ L.T
    D = y @ c  # (reps, n)
    m = D.mean(axis=1)
    s = D.std(axis=1, ddof=1)
    t = m / (s / np.sqrt(n))
    p = 2 * stats.t.sf(np.abs(t), n - 1)
    return (p < ALPHA).mean()


def main():
    rng = np.random.default_rng(SEED)
    print(f"numpy {np.__version__}, scipy {__import__('scipy').__version__}, python {sys.version.split()[0]}")
    print(f"dz={DZ}, alpha={ALPHA} (two-sided), reps per n={REPS}, seed={SEED}")
    print("n, power_sim(rho=0.5), MCSE, power_sim(rho=0.2), analytic(noncentral t)")
    rows = []
    for n in N_GRID:
        p5 = simulate(n, 0.5, rng)
        p2 = simulate(n, 0.2, rng)
        mcse = np.sqrt(p5 * (1 - p5) / REPS)
        pa = analytic_power(n)
        rows.append((n, p5, p2, pa))
        print(f"{n}, {p5:.4f}, {mcse:.4f}, {p2:.4f}, {pa:.4f}")
    # 최소 n (해석해 기준, 1 단위 탐색)
    n_min = next(n for n in range(10, 500) if analytic_power(n) >= TARGET)
    print(f"analytic minimal n for power>={TARGET}: {n_min} (power={analytic_power(n_min):.4f}); "
          f"n-1={n_min-1} (power={analytic_power(n_min-1):.4f})")
    # 경계 근처 정밀 시뮬레이션
    print("boundary check, reps=100000, rho=0.5:")
    for n in range(n_min - 3, n_min + 4):
        ps = simulate(n, 0.5, rng, reps=100000)
        print(f"  n={n}: sim={ps:.4f} (MCSE {np.sqrt(ps*(1-ps)/1e5):.4f}), analytic={analytic_power(n):.4f}")
    sim_first = next((n for n, p5, p2, pa in rows if p5 >= TARGET), None)
    print(f"first grid n with sim power>={TARGET} (rho=0.5): {sim_first}")


if __name__ == "__main__":
    main()
