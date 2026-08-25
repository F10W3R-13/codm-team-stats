# ZCS/RDS 가중치 검증 스크립트 (읽기 전용)
#
# 목적: 현재 공식의 항·가중치가 승패와 맞물리는지 측정 → 재튜닝의 근거 제공.
#   - 각 항의 팀 합계가 승패를 예측하는 힘: AUC (0.5=무관, 1.0=완벽)
#   - 현재 공식(선형 합 / 선수별 clamp 후 합)의 AUC
#   - 표준화 로지스틱 회귀(교차검증)로 "이 데이터가 말하는 이상 방향"
#
# 실행 (배포 DB — 로컬 codm.db는 스태일할 수 있어 진단용으로 부적합):
#   railway run --service Postgres python scripts/zcs_validation.py
# 로컬 강제 실행(경고 출력):
#   python scripts/zcs_validation.py
#
# ⚠️ 이 스크립트는 SELECT만 한다. 공식을 변경하지 않는다 — 변경은 코치 승인 후
# metrics.py + SQL 인라인 5곳 + 테스트 동기 작업으로.

import math
import os
import random
import sqlite3
import sys

# 8·CK + 4.1·(K−CK) = 4.1·K + 3.9·CK (선형 등가형 — 거점 안 킬 8점, 밖 킬 4.1점)
HP_TERMS = [("kills", 4.1), ("deaths", -5.0), ("obj_time", 1.1), ("capture_kill", 3.9)]
SND_TERMS = [("kills", 4.1), ("deaths", -5.0), ("assists", 3.5),
             ("first_kill", 14.0), ("lone_wolf_win", 20.0), ("adr", 0.12)]


# ── 통계 유틸 (의존성 없이) ────────────────────────────────────────────────

def auc(scores, labels):
    """AUC (Mann-Whitney). labels: 1=WIN, 0=LOSS. 0.5=우연."""
    wins = [s for s, lab in zip(scores, labels) if lab == 1]
    losses = [s for s, lab in zip(scores, labels) if lab == 0]
    if not wins or not losses:
        return None
    greater = 0
    for w in wins:
        for lo in losses:
            if w > lo:
                greater += 1
            elif w == lo:
                greater += 0.5
    return greater / (len(wins) * len(losses))


def point_biserial(scores, labels):
    n = len(scores)
    if n < 2:
        return None
    mx = sum(scores) / n
    my = sum(labels) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(scores, labels))
    vx = sum((x - mx) ** 2 for x in scores)
    vy = sum((y - my) ** 2 for y in labels)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def _std(xs):
    mu = sum(xs) / len(xs)
    var = sum((x - mu) ** 2 for x in xs) / len(xs)
    return mu, math.sqrt(var)


def logreg(X, y, l2=1.0, iters=1500, lr=0.3):
    """표준화된 입력용 단순 경사하강 로지스틱 회귀. 계수는 '방향' 참고용."""
    n, d = len(X), len(X[0])
    w = [0.0] * d
    b = 0.0
    for _ in range(iters):
        gw = [0.0] * d
        gb = 0.0
        for xi, yi in zip(X, y):
            z = b + sum(wj * xj for wj, xj in zip(w, xi))
            p = 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))
            err = p - yi
            for j in range(d):
                gw[j] += err * xi[j]
            gb += err
        for j in range(d):
            w[j] -= lr * (gw[j] / n + l2 * w[j] / n)
        b -= lr * gb / n
    return w, b


def logreg_predict(w, b, X):
    out = []
    for xi in X:
        z = b + sum(wj * xj for wj, xj in zip(w, xi))
        out.append(1 / (1 + math.exp(-max(-30.0, min(30.0, z)))))
    return out


def cv_auc(X, y, folds=5, seed=7):
    """k-fold 교차검증 AUC. 표본 부족 시 None."""
    idx = list(range(len(X)))
    random.Random(seed).shuffle(idx)
    chunks = [idx[i::folds] for i in range(folds)]
    oof_scores, oof_labels = [], []
    for k in range(folds):
        test = set(chunks[k])
        tr_X = [X[i] for i in idx if i not in test]
        tr_y = [y[i] for i in idx if i not in test]
        te_X = [X[i] for i in idx if i in test]
        te_y = [y[i] for i in idx if i in test]
        if len(set(tr_y)) < 2 or len(set(te_y)) < 2:
            return None
        w, b = logreg(tr_X, tr_y)
        oof_scores.extend(logreg_predict(w, b, te_X))
        oof_labels.extend(te_y)
    return auc(oof_scores, oof_labels)


# ── DB 접속 ────────────────────────────────────────────────────────────────

def get_conn():
    for var in ("DATABASE_PUBLIC_URL", "DATABASE_URL"):
        url = os.environ.get(var)
        if not url:
            continue
        try:
            import psycopg2
            return psycopg2.connect(url, sslmode="require"), "Postgres(배포)"
        except ImportError:
            break
        except Exception:
            try:
                return psycopg2.connect(url), f"Postgres(배포, {var})"
            except Exception:
                continue
    path = os.environ.get("CODM_DB_PATH", "codm.db")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True), f"로컬 SQLite({path}) ⚠️스태일 가능"


# ── 분석 ───────────────────────────────────────────────────────────────────

def rows_as_dicts(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def analyze(conn, mode, terms):
    sum_parts = ", ".join(f"SUM(s.{t[0]}) AS {t[0]}" for t in terms)
    table = "player_stats_hp" if mode == "HP" else "player_stats_snd"
    rows = rows_as_dicts(
        conn,
        f"""SELECT m.id, m.result, {sum_parts}
            FROM matches m JOIN {table} s ON s.match_id = m.id
            WHERE m.mode = '{mode}' AND m.result IN ('WIN','LOSS')
            GROUP BY m.id, m.result
            HAVING COUNT(s.player_id) >= 4""")

    n = len(rows)
    wins = sum(1 for r in rows if r["result"] == "WIN")
    print(f"\n━━━ {mode}: 결과 보유 매치 {n}개 (W{wins}/L{n-wins}, 승률 {wins/n:.0%}) ━━━")
    if n < 20:
        print("  → 표본 부족 (<20): 회귀 생략, AUC만 참고용으로 출력")
    labels = [1 if r["result"] == "WIN" else 0 for r in rows]

    # 1) 항별 AUC·상관
    print("  [항별 승패 변별력] (팀 합계 기준)")
    feats = []
    for term, _w in terms:
        vals = [r[term] for r in rows]
        a = auc(vals, labels)
        c = point_biserial(vals, labels)
        flag = " ← 데스는 낮을수록 좋음" if term == "deaths" else ""
        print(f"    {term:<14} AUC={a:.3f}  r={c:+.3f}{flag}")
        feats.append(vals)

    # 2) 현재 공식 AUC
    linear = [sum(r[t] * w for t, w in terms) for r in rows]
    print(f"  [현재 공식(선형 합)]        AUC={auc(linear, labels):.3f}")

    # 3) 회귀 (표준화 후)
    if n >= 20:
        zs = []
        for vals in feats:
            mu, sd = _std(vals)
            zs.append([(v - mu) / (sd or 1) for v in vals])
        X = [[z[i] for z in zs] for i in range(n)]
        cv = cv_auc(X, labels)
        w, b = logreg(X, labels)
        print("  [회귀가 말하는 방향] (표준화 계수, |값|=상대 중요도 — 방향 참고용)")
        for (term, cur_w), rc in zip(terms, w):
            print(f"    {term:<14} 현재가중={cur_w:+7.2f}  회귀방향={rc:+.3f}")
        if cv is not None:
            print(f"  [회귀 모델 교차검증 AUC]  {cv:.3f}  (현재 공식 대비 승패 설명력)")
        else:
            print("  [회귀 교차검증] 폴드별 클래스 편중으로 생략")


def main():
    conn, source = get_conn()
    print(f"DB: {source}")
    if "SQLite" in source:
        print("⚠️  로컬 DB는 배포와 다를 수 있습니다(2026-08 실측: 배포 370경기/승패138 vs 로컬 스태일).")
        print("    배포 기준 분석: railway run --service Postgres python scripts/zcs_validation.py")
    analyze(conn, "HP", HP_TERMS)
    analyze(conn, "SND", SND_TERMS)
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
