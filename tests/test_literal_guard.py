"""Checks for invented_values, using SQL the model really produced. Run: python tests/test_literal_guard.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.text_to_sql import invented_values

SHOULD_REJECT = [
    ("How many races did Michael Schumacher win?",
     "SELECT r.driver_name, COUNT(*) AS wins FROM f1_results r JOIN f1_races c USING (season, round) WHERE c.circuit_id = 'monza' AND r.position = 1 GROUP BY r.driver_name"),
    ("How many pole positions does Lewis Hamilton have?",
     "SELECT COUNT(*) FROM f1_results WHERE season = 2018 AND driver_name = 'Lewis Hamilton' AND grid = 1"),
    ("Who started on pole at the 2019 Italian Grand Prix?",
     "SELECT COUNT(*) FROM f1_results WHERE driver_name = 'Jim Clark' AND grid = 1"),
    ("How many Grands Prix did Jim Clark win?",
     "SELECT COUNT(*) FROM f1_results WHERE driver_name = 'Jim Clark' AND race_name = 'British Grand Prix'"),
    ("Who finished second in the 2021 British Grand Prix?",
     "SELECT driver_name FROM f1_results WHERE season = 2021 AND round = 7 AND position = 2 AND race_name = 'British Grand Prix'"),
    ("How many wins did Red Bull have in 2023?",
     "SELECT COUNT(*) FROM f1_results WHERE season = 2023 AND constructor = 'Red Bull' AND position = 1 AND race_name LIKE '%Monaco Grand Prix%'"),
    ("Which driver has started the most races?",
     "SELECT driver_name, COUNT(*) FROM f1_results WHERE driver_name LIKE '%Lewis%' AND season = 2023 GROUP BY driver_name"),
    ("Which team has the most constructors championships?",
     "SELECT constructor FROM f1_constructor_standings WHERE season = 2011 AND position = 1"),
    ("Which team has the most constructors championships?",
     "SELECT constructor FROM f1_results WHERE status = 'Champion' GROUP BY constructor"),
    ("How many Grands Prix did Jim Clark win?",
     "SELECT COUNT(*) FROM f1_results WHERE driver_name = 'Jim Clark' AND season = '1963' AND position = 1"),
]

SHOULD_PASS = [
    ("What was Lewis Hamilton's points total in 2020?",
     "SELECT SUM(points) AS total FROM f1_results WHERE season = 2020 AND driver_name = 'Lewis Hamilton'"),
    ("How many wins does Hamilton have?",
     "SELECT COUNT(*) FROM f1_results WHERE driver_name = 'Lewis Hamilton' AND position = 1"),
    ("How many podiums did Kimi Raikkonen score?",
     "SELECT COUNT(*) FROM f1_results WHERE driver_name = 'Kimi Räikkönen' AND position <= 3"),
    ("Who had the most wins for Ferrari in the 2000s?",
     "SELECT driver_name, COUNT(*) FROM f1_results WHERE constructor = 'Ferrari' AND season BETWEEN 2000 AND 2009 AND position = 1 GROUP BY 1 LIMIT 10"),
    ("Which driver won the most races at Hockenheim?",
     "SELECT r.driver_name FROM f1_results r JOIN f1_races c USING (season, round) WHERE c.circuit_id = 'hockenheimring' AND r.position = 1 LIMIT 1"),
    ("Who won the 2021 Abu Dhabi Grand Prix?",
     "SELECT T1.driver_name FROM f1_results AS T1 WHERE season = 2021 AND race_name LIKE '%Abu Dhabi%' AND position = 1"),
    ("How many races did Sebastian Vettel fail to finish in 2014?",
     "SELECT COUNT(*) FROM f1_results WHERE driver_name = 'Sebastian Vettel' AND season = 2014 AND status <> 'Finished' AND status <> 'Lapped' AND status NOT LIKE '+%'"),
]

# Known gap: the guard only checks values, so a wrong query using the question's own words passes.
KNOWN_GAP = ("How many Grands Prix did Jim Clark win?",
             "SELECT COUNT(*) FROM f1_results WHERE driver_name = 'Jim Clark' AND status = 'win'")

failures = 0
for question, sql in SHOULD_REJECT:
    if not invented_values(sql, question):
        failures += 1
        print(f"MISSED: {question}\n  {sql}")
for question, sql in SHOULD_PASS:
    found = invented_values(sql, question)
    if found:
        failures += 1
        print(f"FALSE ALARM {found}: {question}\n  {sql}")
assert invented_values(*KNOWN_GAP) == [], "known gap closed, move this to SHOULD_REJECT"

print(f"{len(SHOULD_REJECT) + len(SHOULD_PASS) - failures}/{len(SHOULD_REJECT) + len(SHOULD_PASS)} passed")
sys.exit(1 if failures else 0)
