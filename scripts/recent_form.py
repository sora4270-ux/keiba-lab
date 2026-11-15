"""Recent NAR form from completed races strictly before the target date."""
from collections import defaultdict
import datetime as dt
import math
import re
import unicodedata

LOOKBACK_DAYS = 90
RECENCY = (3, 2, 1)


def horse_key(row):
    name = unicodedata.normalize("NFKC", row.get("馬名", "")).strip()
    birth = row.get("生年月日", "")
    return "\t".join((name, birth)) if name and re.fullmatch(r"\d{8}", birth) else None


def key(row):
    return row.get("競馬場", ""), row.get("競走年月日", ""), row.get("レース番号", "")


def race_time(value):
    """Monthly CSV uses minute, two second digits, and a tenth."""
    if not re.fullmatch(r"\d{3,4}", value):
        return None
    minutes, seconds = int(value[:-3] or "0"), int(value[-3:]) / 10
    return minutes * 60 + seconds if seconds < 60 and minutes * 60 + seconds > 0 else None


def corner_positions(value):
    """Horses shown together in parentheses share the group's mean rank."""
    value = unicodedata.normalize("NFKC", value).replace(" ", "")
    if not re.fullmatch(r"[0-9,()=\-]+", value):
        return {}
    positions = {}
    rank = 0
    for group in re.findall(r"\([0-9,]+\)|\d+", value):
        numbers = [int(n) for n in re.findall(r"\d+", group)]
        midpoint = rank + (len(numbers)-1)/2
        if len(set(numbers)) != len(numbers) or any(n in positions or not 1 <= n <= 30 for n in numbers):
            return {}
        positions.update((n, midpoint) for n in numbers)
        rank += len(numbers)
    if rank < 3:
        return {}
    return {n: 1 - pos/(rank-1) for n, pos in positions.items()}


def history_runs(tables, history):
    """Keep derived ratings in memory. Neither program reads today's results."""
    metadata = {}
    for _, row in tables["racelist"]:
        race = key(row)
        if not race[0] or not re.fullmatch(r"\d{8}", race[1]) or not re.fullmatch(r"\d{1,2}", race[2]):
            continue
        distance = row.get("距離", "")
        distance = int(distance) if distance.isdecimal() else 0
        corners = {}
        for i in range(1, 9):
            label = unicodedata.normalize("NFKC", row.get(f"コーナー名称{i}", "")).strip()
            if label.endswith(("4角", "4コーナー")):
                corners = corner_positions(row.get(f"コーナー通過順{i}", ""))
        metadata[race] = (distance, corners)
    finishes = defaultdict(list)
    for _, row in tables["horselist"]:
        race = key(row)
        if race not in metadata:
            continue
        rank, no = row.get("着順", ""), row.get("馬番", "")
        ident, finish_time = horse_key(row), race_time(row.get("タイム", ""))
        if ident and rank.isdecimal() and 1 <= int(rank) <= 30 and no.isdecimal():
            finishes[race].append((int(rank), int(no), ident, finish_time))
    for race, finish in finishes.items():
        winners = [time for rank, _, _, time in finish if rank == 1 and time]
        winner = min(winners, default=None)
        distance, corners = metadata[race]
        for _, no, ident, time in finish:
            score = None
            if winner and time and 600 <= distance <= 4000 and no in corners:
                gap = max(0, time-winner) * 1000/distance
                margin = math.exp(-gap/1.5)
                score = .75*margin + .25*corners[no]
            history.setdefault(ident, {})[race] = score


def features_on(history, target):
    earliest = (dt.date.fromisoformat(target)-dt.timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
    cutoff = target.replace("-", "")
    features = {}
    for horse, runs in history.items():
        latest = sorted((race for race in runs if earliest <= race[1] < cutoff),
                        key=lambda r: (r[1], int(r[2])), reverse=True)[:len(RECENCY)]
        usable = [(w, runs[race]) for w, race in zip(RECENCY, latest) if runs[race] is not None]
        if usable:
            # Equivalent to one neutral run; shrinks sparse form toward .5.
            score = (.5 + sum(w*p for w, p in usable))/(1+sum(w for w, _ in usable))
            features[horse] = (round(score, 5), len(usable))
    return features


def recent_adjustment(weights, field_features):
    adjusted = [weight * math.exp(.9*(feature[0]-.5)) if feature else weight
                for weight, feature in zip(weights, field_features)]
    total = sum(adjusted)
    return [p/total for p in adjusted]
