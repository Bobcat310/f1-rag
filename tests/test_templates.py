"""Checks templates against separately written SQL. Run: python tests/test_templates.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.templates import focus_lines, template_answer
from src.text_to_sql import asks_for_missing_field, con, invented_values, NOT_IN_DATA


def one(sql: str):
    return con.execute(sql).fetchone()[0]


def number(question: str, truth_sql: str):
    answer = template_answer(question)
    assert answer, f"no template for: {question}"
    expected = f"{one(truth_sql):g}"
    assert f" {expected} " in answer["answer"], f"{question}: {answer['answer']} != {expected}"


def name(question: str, expected: str):
    answer = template_answer(question)
    assert answer, f"no template for: {question}"
    assert expected in answer["answer"], f"{question}: {answer['answer']}"


def declined(question: str):
    assert template_answer(question) is None, f"should go to the model: {question}"


number("How many races did Fernando Alonso win?", "SELECT COUNT(*) FROM f1_results WHERE driver_id = 'alonso' AND position = 1")
number("How many wins did Hamilton have in 2020?", "SELECT COUNT(*) FROM f1_results WHERE driver_id = 'hamilton' AND season = 2020 AND position = 1")
number("How many pole positions did Ayrton Senna take?", "SELECT COUNT(*) FROM f1_results WHERE driver_id = 'senna' AND grid = 1")
number("How many podiums did Kimi Raikkonen score?", "SELECT COUNT(*) FROM f1_results WHERE driver_id = 'raikkonen' AND position <= 3")
number("How many wins did Ferrari have in the 2000s?", "SELECT COUNT(DISTINCT season * 100 + round) FROM f1_results WHERE constructor = 'Ferrari' AND season BETWEEN 2000 AND 2009 AND position = 1")
number("How many wins did Hamilton have for McLaren?", "SELECT COUNT(*) FROM f1_results WHERE driver_id = 'hamilton' AND constructor = 'McLaren' AND position = 1")
number("How many points did Max Verstappen score in 2021?", "SELECT s.points FROM f1_driver_standings s WHERE s.season = 2021 AND s.driver_id = 'max_verstappen'")
number("How many points did McLaren score in 2024?", "SELECT points FROM f1_constructor_standings WHERE season = 2024 AND constructor = 'McLaren'")
number("How many Grands Prix did Niki Lauda win?", "SELECT COUNT(*) FROM f1_results WHERE driver_id = 'lauda' AND position = 1")
number("How many times did Jean Alesi retire in 1995?", "SELECT COUNT(*) FROM f1_results WHERE driver_id = 'alesi' AND season = 1995 AND status <> 'Finished' AND status <> 'Lapped' AND status NOT LIKE '+%'")
number("How many points did Max Verstappen score?", "SELECT (SELECT SUM(points) FROM f1_results WHERE driver_id = 'max_verstappen') + (SELECT SUM(points) FROM f1_sprint_results WHERE driver_id = 'max_verstappen')")
number("How many pit stops did Lewis Hamilton make in 2023?", "SELECT COUNT(*) FROM f1_pit_stops WHERE driver_id = 'hamilton' AND season = 2023")
number("How many pit stops did Lewis Hamilton make at the 2023 Monaco Grand Prix?", "SELECT COUNT(*) FROM f1_pit_stops p JOIN f1_races r USING (season, round) WHERE p.driver_id = 'hamilton' AND p.season = 2023 AND r.race_name = 'Monaco Grand Prix'")
assert "isn't in the data" in template_answer("How many pit stops did Michael Schumacher make in 2004?")["answer"]
assert " 0 " in template_answer("How many races did Lewis Hamilton not finish in 2017?")["answer"]
number("How many sprint wins did Max Verstappen have in 2022?", "SELECT COUNT(*) FROM f1_sprint_results WHERE driver_id = 'max_verstappen' AND season = 2022 AND position = 1")
number("How many sprint points did McLaren score in 2024?", "SELECT SUM(points) FROM f1_sprint_results WHERE constructor = 'McLaren' AND season = 2024")
declined("How many sprint wins did Max Verstappen have in 2019?")  # no sprints before 2021
declined("Who has the most sprint wins?")
assert not asks_for_missing_field("How many sprint wins did Lando Norris have?")

name("Who won the 2003 Canadian Grand Prix?", "Michael Schumacher")
name("Who won the 2021 Abu Dhabi GP?", "Max Verstappen")
name("Who won the 2019 race at Monza?", "Charles Leclerc")
name("Which team won the 2021 Monaco Grand Prix?", "Red Bull")
name("Who started on pole at the 2017 Hungarian Grand Prix?", "Sebastian Vettel")
name("Who won the 1951 Indianapolis 500?", "Lee Wallard")
name("Who won the 2021 drivers championship?", "Max Verstappen")
name("Which team won the 2011 constructors championship?", "Red Bull")
name("Who was world champion in 1988?", "Ayrton Senna")
name("Which driver won the most races in 1988?", "Ayrton Senna")
name("Which team has the most wins in the 1990s?", "Williams")
name("Who has the most pole positions?", "Lewis Hamilton")

declined("How many wins did Schumacher have?")          # Michael and Ralf both won races
declined("How many wins did Hamilton have at Monza?")   # a word the template can't use
declined("How many wins did Hamilton have from pole?")
declined("How many consecutive wins did Vettel have in 2013?")
declined("How many championships did Hamilton win?")
declined("How many wins did Lewis Hamilton have in 1990?")  # never raced then
declined("Who finished second in the 2021 Abu Dhabi Grand Prix?")
declined("Who finished second in the 2021 drivers championship?")
declined("Who won the British Grand Prix?")             # no season
declined("Who won the 2026 drivers championship?")      # season still running
declined("Who won the 2020 race at Silverstone?")       # two races there that year
declined("Which driver won the most races for Ferrari?")
declined("Which driver scored the most points in 2021?")

for question in ("How many fans watched the 2019 British Grand Prix?", "Who was the team principal of Red Bull in 2015?",
                 "How tall is Lando Norris?", "How much does a Ferrari engine cost?"):
    assert asks_for_missing_field(question), question
for question in ("How many wins did Senna have?", "Who was the youngest winner?", "Who was the 2021 champion?", "How many laps did Senna complete?"):
    assert not asks_for_missing_field(question), question

assert NOT_IN_DATA.search("How many laps did Max Verstappen lead in 2023?")
assert NOT_IN_DATA.search("Who is the race engineer of Lewis Hamilton?")
assert not NOT_IN_DATA.search("Who led the 2021 drivers championship?")
assert invented_values("SELECT driver_name FROM f1_results WHERE season = 2021 AND round = 1", "Who won in 2021?")
assert not invented_values("SELECT driver_name FROM f1_results WHERE season = 2021 AND round = 1", "Who won round 1 of 2021?")
assert not invented_values("SELECT * FROM f1_results r JOIN f1_races c ON r.round = c.round WHERE r.season = 2021", "Who won in 2021?")

assert focus_lines("Tell me about the 2011 Monaco Grand Prix") == ["The 2011 Monaco Grand Prix "]
assert focus_lines("Why did Max Verstappen not finish the 2021 British Grand Prix?") == [
    "In the 2021 British Grand Prix, Max Verstappen ", "The 2021 British Grand Prix "]
assert focus_lines("Describe Damon Hill's 1996 season") == []

print("template checks passed")
