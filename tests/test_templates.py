"""Checks templates against separately written SQL. Run: python tests/test_templates.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.templates import focus_lines, template_answer
from src.text_to_sql import asks_for_missing_field, build_prompt, con, invented_values, NOT_IN_DATA


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
LOTUS_WINS = "SELECT COUNT(DISTINCT season * 100 + round) FROM f1_results WHERE position = 1 AND constructor LIKE '%Lotus%'"
CLASSIC_LOTUS = "(constructor = 'Team Lotus' OR constructor LIKE 'Lotus-%')"
number("How many wins did Lotus have?", LOTUS_WINS)
number("How many wins did Team Lotus have?", f"SELECT COUNT(DISTINCT season * 100 + round) FROM f1_results WHERE position = 1 AND {CLASSIC_LOTUS}")
number("How many wins did Lotus F1 have?", "SELECT COUNT(*) FROM f1_results WHERE position = 1 AND constructor = 'Lotus F1'")
number("How many wins did Lotus-Climax have?", "SELECT COUNT(DISTINCT season * 100 + round) FROM f1_results WHERE position = 1 AND constructor = 'Lotus-Climax'")
number("How many wins did Jim Clark have for Lotus?", "SELECT COUNT(*) FROM f1_results WHERE driver_id = 'clark' AND position = 1 AND constructor LIKE '%Lotus%'")
for team in ("Cooper", "Brabham", "McLaren", "BRM", "Matra"):
    number(f"How many wins did {team} have?", f"SELECT COUNT(DISTINCT season * 100 + round) FROM f1_results WHERE position = 1 AND split_part(constructor, '-', 1) = '{team}'")
number("How many poles did Lotus have in the 1960s?", f"SELECT COUNT(DISTINCT season * 100 + round) FROM f1_results WHERE grid = 1 AND season BETWEEN 1960 AND 1969 AND constructor LIKE '%Lotus%'")
number("How many points did Lotus score in 1965?", "SELECT SUM(points) FROM f1_constructor_standings WHERE season = 1965 AND constructor LIKE '%Lotus%'")
assert "three separate teams" in template_answer("How many wins did Lotus have?")["answer"]
assert "three separate teams" not in template_answer("How many wins did Team Lotus have?")["answer"]
assert "three separate teams" not in template_answer("How many wins did Lotus have in 1963?")["answer"]
assert "Brabham-Repco 67, Brabham-Climax 2" in template_answer("How many points did Brabham score in 1967?")["answer"]
assert "entries" not in template_answer("How many points did McLaren score in 2024?")["answer"]
name("Which team has the most wins in the 1960s?", one("""SELECT CASE WHEN constructor LIKE '%Lotus%' THEN 'Team Lotus' ELSE split_part(constructor, '-', 1) END t
    FROM f1_results WHERE position = 1 AND season BETWEEN 1960 AND 1969 GROUP BY 1 ORDER BY COUNT(DISTINCT season * 100 + round) DESC LIMIT 1"""))
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
number("How many wins did Hamilton have at Monza?", """SELECT COUNT(*) FROM f1_results r JOIN f1_races c USING (season, round)
    WHERE r.driver_id = 'hamilton' AND c.circuit_id = 'monza' AND r.position = 1""")
number("How many times did Ayrton Senna win the Monaco Grand Prix?", "SELECT COUNT(*) FROM f1_results WHERE driver_id = 'senna' AND race_name = 'Monaco Grand Prix' AND position = 1")
number("How many races did Brabham win altogether?", "SELECT COUNT(DISTINCT season * 100 + round) FROM f1_results WHERE constructor LIKE 'Brabham%' AND position = 1")
number("How many wins did Williams rack up during the 1980s?", "SELECT COUNT(DISTINCT season * 100 + round) FROM f1_results WHERE constructor = 'Williams' AND position = 1 AND season BETWEEN 1980 AND 1989")
number("How many wins did Juan Manuel Fangio have?", "SELECT COUNT(*) FROM f1_results WHERE driver_id = 'fangio' AND position = 1")
number("How many pit stops were made in total during the 2021 Hungarian Grand Prix?", "SELECT COUNT(*) FROM f1_pit_stops WHERE season = 2021 AND race_name = 'Hungarian Grand Prix'")
declined("How many pit stops were made in 2021?")  # a whole season of every car's stops
name("Who was crowned Formula 1 world champion in 1992?", "Nigel Mansell")
name("Who came home in third place at the 2005 Japanese Grand Prix?", "Fernando Alonso")
name("Which track has held more Grands Prix than any other circuit?", "Monza")
name("Who has more wins than any other driver?", "Lewis Hamilton")
declined("How many wins did Hamilton have from pole?")
declined("How many consecutive wins did Vettel have in 2013?")
declined("How many championships did Hamilton win?")
declined("How many wins did Lewis Hamilton have in 1990?")  # never raced then
PLACED = "SELECT driver_name FROM f1_results r JOIN f1_races c USING (season, round) WHERE r.season = {} AND c.race_name = '{}' AND r.position = {}"
name("Who finished second in the 2021 Abu Dhabi Grand Prix?", one(PLACED.format(2021, "Abu Dhabi Grand Prix", 2)))
name("Who came third at the 2018 Belgian Grand Prix?", one(PLACED.format(2018, "Belgian Grand Prix", 3)))
name("Who placed 5th in the 2019 race at Monza?", one(PLACED.format(2019, "Italian Grand Prix", 5)))
assert "finished 2nd in the 2021 Abu Dhabi Grand Prix" in template_answer("Who finished second in the 2021 Abu Dhabi Grand Prix?")["answer"]
declined("Who finished second in the 2021 drivers championship?")
declined("Who finished second most often in 2021?")
declined("Who won the British Grand Prix?")             # no season
declined("Who won the 2026 drivers championship?")      # season still running
declined("Who won the 2020 race at Silverstone?")       # two races there that year
declined("Which driver won the most races for Ferrari?")
name("Which driver scored the most points in 2021?", one("""SELECT d.given_name || ' ' || d.family_name FROM f1_driver_standings s
    JOIN f1_drivers d USING (driver_id) WHERE s.season = 2021 ORDER BY s.points DESC LIMIT 1"""))
name("Which team scored the most points in 1967?", "Brabham")  # its two entries are added together
name("Who has scored the most points?", one("""SELECT name FROM (SELECT driver_name AS name, points FROM f1_results
    UNION ALL SELECT driver_name, points FROM f1_sprint_results) GROUP BY 1 ORDER BY SUM(points) DESC LIMIT 1"""))
assert "so far" in template_answer("Who has the most points in 2026?")["answer"]
declined("Who scored the most sprint points in 2023?")
number("Number of pole positions for Jim Clark?", "SELECT COUNT(*) FROM f1_results WHERE driver_id = 'clark' AND grid = 1")
number("In 1988, how many wins did Ayrton Senna have?", "SELECT COUNT(*) FROM f1_results WHERE driver_id = 'senna' AND season = 1988 AND position = 1")
name("In the 1970s, which driver stood on the podium the most times?", one("""SELECT driver_name FROM f1_results
    WHERE season BETWEEN 1970 AND 1979 AND position <= 3 GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1"""))
declined("In what year did Senna win?")

for question in ("How many fans watched the 2019 British Grand Prix?", "Who was the team principal of Red Bull in 2015?",
                 "How tall is Lando Norris?", "How much does a Ferrari engine cost?"):
    assert asks_for_missing_field(question), question
for question in ("How many wins did Senna have?", "Who was the youngest winner?", "Who was the 2021 champion?", "How many laps did Senna complete?",
                 "Which team won the 2011 constructors championship?", "Which driver has the most wins?", "Which country hosted the most races?"):
    assert not asks_for_missing_field(question), question
for question in ("Which company made the brakes for Ferrari in 2004?", "Which engineer worked with Senna?"):
    assert asks_for_missing_field(question), question
for question in ("What is the top speed of a Red Bull RB19?", "What was Max Verstappen's top speed at Monza in 2023?",
                 "What fuel does Mercedes use?", "What brand of helmet does Charles Leclerc wear?",
                 "Which driver has the most Instagram followers?", "Who will win the 2026 drivers championship?",
                 "How much did the Las Vegas circuit cost?", "What colours did Jordan race in?"):
    assert NOT_IN_DATA.search(question) or asks_for_missing_field(question), question
for question in ("What was Lewis Hamilton's points total in 2020?", "What is the average points scored by Mercedes per season?",
                 "What team did Sebastian Vettel drive for in 2015?", "What happened at the 2010 Bahrain Grand Prix?",
                 "What is the name of the circuit in Monza?", "What year did Ayrton Senna win his first title?",
                 "Who has the most career podiums?", "Who is the most successful driver?",
                 # wordings a noun allow-list refused on new questions
                 "What's Nelson Piquet's career tally of wins?", "What was McLaren's final points haul in 1988?",
                 "In 1982, how many teams won at least one race?", "Brabham were strong in 1983 - how many did they win?",
                 "What should I know about Interlagos?", "What was the quickest pit stop anyone recorded in 2019?"):
    assert not (NOT_IN_DATA.search(question) or asks_for_missing_field(question)), question
name("What was the average pit stop time at the 2020 Italian Grand Prix?", f"{one('''SELECT ROUND(AVG(duration), 2) FROM f1_pit_stops
    WHERE season = 2020 AND race_name = 'Italian Grand Prix' AND duration <= 120'''):.2f}")

assert NOT_IN_DATA.search("How many laps did Max Verstappen lead in 2023?")
assert NOT_IN_DATA.search("Who is the race engineer of Lewis Hamilton?")
assert not NOT_IN_DATA.search("Who led the 2021 drivers championship?")
assert invented_values("SELECT driver_name FROM f1_results WHERE season = 2021 AND round = 1", "Who won in 2021?")
assert not invented_values("SELECT driver_name FROM f1_results WHERE season = 2021 AND round = 1", "Who won round 1 of 2021?")
assert not invented_values("SELECT * FROM f1_results r JOIN f1_races c ON r.round = c.round WHERE r.season = 2021", "Who won in 2021?")

AVERAGE = "SELECT ROUND(AVG(duration), 2) FROM f1_pit_stops WHERE duration <= 120 AND season = 2021"
assert f"{one(AVERAGE):.2f}" in template_answer("What was the average pit stop time in 2021?")["answer"]
assert f"{one(AVERAGE + " AND driver_id = 'hamilton'"):.2f}" in template_answer("What was the average pit stop time for Lewis Hamilton in 2021?")["answer"]
assert "isn't in the data" in template_answer("What was the average pit stop time in 2004?")["answer"]
declined("What was the average pit stop time?")
for question in ("Who designed the Williams FW14B?", "Who owns the Haas team?"):
    assert NOT_IN_DATA.search(question), question
assert not NOT_IN_DATA.search("How many wins did Lewis Hamilton score on his own?")

assert not invented_values("SELECT COUNT(*) FROM f1_results WHERE constructor LIKE '%Brabham%' AND grid = 1 AND position = 1", "How many wins from pole did Brabham have?")
for question, note in (("How many wins from pole did Brabham have?", "LIKE '%Name%'"), ("How many wins do British drivers have?", "f1_drivers"),
                       ("How many laps did Senna complete?", "laps column"), ("What was the average pit stop time in 2022?", "duration <= 120")):
    assert note in build_prompt(question), question
assert "nationality" not in build_prompt("Who won the 2003 British Grand Prix?")

assert focus_lines("Tell me about the 2011 Monaco Grand Prix") == ["The 2011 Monaco Grand Prix "]
assert focus_lines("Why did Max Verstappen not finish the 2021 British Grand Prix?") == [
    "In the 2021 British Grand Prix, Max Verstappen ", "The 2021 British Grand Prix "]
assert focus_lines("Describe Damon Hill's 1996 season") == ["At the end of the 1996 season, Damon Hill "]
assert focus_lines("Describe Lando Norris's 2026 season") == ["After round 18 of the 2026 season, Lando Norris "]
assert focus_lines("Which races were held in 1996?") == []
assert focus_lines("Tell me about Lewis Hamilton") == ["Lewis Hamilton raced in Formula 1 "]
assert focus_lines("Compare Ayrton Senna and Alain Prost") == ["Ayrton Senna raced in Formula 1 ", "Alain Prost raced in Formula 1 "]
assert focus_lines("Tell me about Brabham-Repco") == ["Brabham-Repco raced in Formula 1 "]
assert set(focus_lines("Tell me about Lotus")) == {"Lotus raced in Formula 1 ", "Team Lotus raced in Formula 1 ", "Lotus F1 raced in Formula 1 "}
assert focus_lines("Who won the British Grand Prix?") == []
assert focus_lines("Tell me about the Spa-Francorchamps circuit") == ["Circuit de Spa-Francorchamps in "]
assert focus_lines("Tell me about Monza") == ["Autodromo Nazionale di Monza in "]
assert focus_lines("Describe the Red Bull Ring") == ["Red Bull Ring in "]
assert focus_lines("Tell me about George Russell") == ["George Russell raced in Formula 1 "]
assert focus_lines("Tell me about racing in Barcelona") == []  # three circuits there
assert focus_lines("I'd love some background on the Tyrrell team.") == ["Tyrrell raced in Formula 1 "]  # not John Love
assert focus_lines("Give me a rundown of Juan Manuel Fangio's career") == ["Juan Fangio raced in Formula 1 "]
assert focus_lines("What sort of season did Jenson Button have in 2009?") == ["At the end of the 2009 season, Jenson Button "]
for question in ("What kind of year did Kimi Raikkonen have in 2007?", "What's the story of Monza?"):
    assert not asks_for_missing_field(question), question
assert NOT_IN_DATA.search("What's the top speed of a Ferrari?")
for question in ("How many safety cars were there in the 2020 Tuscan Grand Prix?", "Who was Driver of the Day in Monaco 2023?",
                 "What strategy did Ferrari use at Silverstone in 2022?", "How much prize money did Williams get?"):
    assert NOT_IN_DATA.search(question) or asks_for_missing_field(question), question
assert not asks_for_missing_field("How long was the fastest pit stop in 2023?")
assert asks_for_missing_field("How long is the Monza circuit?")

# wording from the seventh blind set
number("Total number of race wins for Williams, all time?",
       "SELECT COUNT(DISTINCT season * 100 + round) FROM f1_results WHERE constructor LIKE 'Williams%' AND position = 1")
name("Who collected the most podium finishes between 2000 and 2009?", "Michael Schumacher")
name("Who collected the most podium finishes between 2000 and 2009?", "with {:g}.".format(one(
    "SELECT COUNT(*) FROM f1_results WHERE driver_name = 'Michael Schumacher' AND season BETWEEN 2000 AND 2009 AND position <= 3")))
name("Which team started from pole most often during the 2010s?", "Mercedes")
name("Which constructor finished top of the 1975 constructors' championship?", "Ferrari won the 1975 constructors")
declined("Who finished second in the 2010 championship?")
number("On average, how long did a pit stop take at the 2018 Hungarian Grand Prix?",
       "SELECT ROUND(AVG(duration), 2) FROM f1_pit_stops WHERE season = 2018 AND race_name = 'Hungarian Grand Prix' AND duration <= 120")
name("Who won the Monaco 88 race?", "Alain Prost")
assert focus_lines("jerez 97, the title decider - who was on pole?") == ["The 1997 European Grand Prix "]
declined("How many 97 wins did Senna have?")  # a two-digit number counts as a year only after a place

# counting the events themselves
number("how many sprints were there in the 2024 season", "SELECT COUNT(DISTINCT round) FROM f1_sprint_results WHERE season = 2024")
number("How many circuits has the French Grand Prix been held at?",
       "SELECT COUNT(DISTINCT circuit_id) FROM f1_races WHERE race_name = 'French Grand Prix'")
number("How many races were held at Monza?",
       "SELECT COUNT(*) FROM f1_races WHERE circuit_id = 'monza' AND (season, round) IN (SELECT season, round FROM f1_results)")
number("How many races were there in 1988?", "SELECT COUNT(*) FROM f1_races WHERE season = 1988")
name("How many races were there in 2026?", "have been run so far")
name("How many races has Lewis Hamilton won?", "Lewis Hamilton had 106 wins")  # still a driver's count

# a team and a season pin the constructors table and its two leading drivers
assert focus_lines("How did Ferrari's 1979 season go?") == [
    "In the 1979 constructors championship, Ferrari ", "At the end of the 1979 season, Jody Scheckter ",
    "At the end of the 1979 season, Gilles Villeneuve "]
assert focus_lines("Who won at the Red Bull Ring in 2020?") == []
assert focus_lines("Who was Mercedes' reserve driver in the 2022 season?") == []
assert focus_lines("Compare Lewis Hamilton and Max Verstappen.") == [
    "Lewis Hamilton raced in Formula 1 ", "Max Verstappen raced in Formula 1 "]
assert focus_lines("Vettel or Alonso - whose career was more successful?") == [
    "Sebastian Vettel raced in Formula 1 ", "Fernando Alonso raced in Formula 1 "]

assert NOT_IN_DATA.search("What position was Lewis Hamilton running in on lap 30 of the 2021 Sao Paulo Grand Prix?")
assert not NOT_IN_DATA.search("On which lap did Hamilton make his first pit stop in the 2021 Sao Paulo Grand Prix?")

print("template checks passed")
