"""Checks for the sentence templates. Run: python tests/test_text_gen.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.text_gen import (career_to_text, circuit_to_text, constructor_standing_to_text, number, race_summary_to_text, result_to_text,
                          standing_to_text, team_families, team_history_to_text)

result = {"season": 2021, "race_name": "Abu Dhabi Grand Prix", "driver_name": "Max Verstappen", "position": 1,
          "grid": 1, "status": "Finished", "points": 25.0, "constructor": "Red Bull", "fastest_lap_rank": 2}
assert result_to_text(result) == ("In the 2021 Abu Dhabi Grand Prix, Max Verstappen finished 1st (winner) "
                                  "starting from position 1, scoring 25.0 points for Red Bull.")

crash = {**result, "position": 20, "status": "Collision", "points": 0.0}
assert result_to_text(crash) == ("In the 2021 Abu Dhabi Grand Prix, Max Verstappen retired (Collision), grid position 1, "
                                 "scoring 0.0 points for Red Bull.")
assert "retired (Out of fuel) but was classified 6th" in result_to_text({**crash, "position": 6, "status": "Out of fuel", "points": 8.0})
assert "was disqualified" in result_to_text({**crash, "status": "Disqualified"})
assert "finished 22nd" in result_to_text({**result, "position": 22, "status": "+1 Lap"})
assert "finished 13th" in result_to_text({**result, "position": 13, "status": "Lapped"})

driver = {"season": 2026, "position": 2, "points": 63.0, "wins": 1, "driver_id": "russell",
          "driver_name": "George Russell", "constructor": "Mercedes"}
assert standing_to_text(driver) == ("At the end of the 2026 season, George Russell was 2nd in the drivers championship "
                                    "with 63.0 points and 1 win, driving for Mercedes.")
assert standing_to_text(driver, after_round=18).startswith("After round 18 of the 2026 season, George Russell was 2nd")
assert "was not classified in the drivers championship with 63.0 points" in standing_to_text({**driver, "position": None})
assert "George Russell won the drivers championship" in standing_to_text({**driver, "position": 1})
assert "George Russell led the drivers championship" in standing_to_text({**driver, "position": 1}, after_round=18)
assert standing_to_text(driver, season=(["Williams", "Mercedes"], 21, 1, 2, 0)).endswith(
    "driving for Williams and Mercedes, from 21 races with 1 pole position, 2 podiums and 0 races not finished.")

team = {"season": 2026, "position": 1, "points": 100.0, "wins": 3, "constructor": "Mercedes"}
assert constructor_standing_to_text(team) == "In the 2026 constructors championship, Mercedes won the title with 100.0 points and 3 wins."
assert "won" not in constructor_standing_to_text(team, after_round=18)
assert "finished 2nd" in constructor_standing_to_text({**team, "position": 2})
assert "McLaren was not classified with 0.0 points and 8 wins" in constructor_standing_to_text(
    {"season": 2007, "position": None, "points": 0.0, "wins": 8, "constructor": "McLaren"})

assert "retired, grid position 1" in result_to_text({**crash, "status": "Retired"})
assert "retired (Engine), no grid position recorded" in result_to_text({**crash, "status": "Engine", "grid": 0})
assert "finished 22nd with no grid position recorded" in result_to_text({**result, "position": 22, "status": "+1 Lap", "grid": 0})
assert result_to_text({**crash, "status": "Fatal accident"}) == (
    "In the 2021 Abu Dhabi Grand Prix, Max Verstappen suffered a fatal accident while driving for Red Bull.")

assert [number(12099.27), number(5259.5), number(25.0), number(0)] == ["12099.27", "5259.5", "25", "0"]

families = team_families(["Lotus-Ford", "Team Lotus", "Lotus F1", "Lotus", "Talbot-Lago", "Cooper", "Cooper-Climax"])
assert sorted(families["Team Lotus"]) == ["Lotus-Ford", "Team Lotus"]
assert families["Lotus"] == ["Lotus"] and families["Lotus F1"] == ["Lotus F1"]
assert sorted(families["Cooper"]) == ["Cooper", "Cooper-Climax"]
assert "Talbot" not in families

career = pd.DataFrame([{"season": 2020, "team": "Williams", "position": 1, "grid": 1}, {"season": 2021, "team": "Williams", "position": 3, "grid": 2},
                       {"season": 2021, "team": "Mercedes", "position": 5, "grid": 3}])
assert career_to_text("George Russell", career, [2021], 50.5) == (
    "George Russell raced in Formula 1 from 2020 to 2021, entering 3 races for Williams and Mercedes, "
    "with 1 win, 1 pole position, 2 podiums and 50.5 points. George Russell won 1 drivers championship (2021).")

shared_win = pd.DataFrame([{"season": 1956, "round": 1, "position": 1, "grid": 1, "driver_name": "Luigi Musso"},
                           {"season": 1956, "round": 1, "position": 1, "grid": 2, "driver_name": "Juan Fangio"},
                           {"season": 1956, "round": 2, "position": 2, "grid": 1, "driver_name": "Juan Fangio"}])
assert "entering 2 races, with 1 win, 2 pole positions" in team_history_to_text("Ferrari", shared_win, [], 10.0)
assert "Juan Fangio and Luigi Musso, with 1 win each" in team_history_to_text("Ferrari", shared_win, [], 10.0)
assert circuit_to_text("Monza in Italy", shared_win) == (
    "Monza in Italy hosted 2 Formula 1 races in 1956. The most wins there came from Juan Fangio, with 2 wins.")

race = pd.DataFrame([
    {"driver_name": "Lando Norris", "constructor": "McLaren", "position": 2, "grid": 1},
    {"driver_name": "Max Verstappen", "constructor": "Red Bull", "position": 1, "grid": 3},
    {"driver_name": "Oscar Piastri", "constructor": "McLaren", "position": 3, "grid": 2},
    {"driver_name": "George Russell", "constructor": "Mercedes", "position": 4, "grid": 4},
])
assert race_summary_to_text(2025, "Dutch Grand Prix", race) == (
    "The 2025 Dutch Grand Prix was won by Max Verstappen for Red Bull, with Lando Norris on pole position, "
    "and the podium was Max Verstappen, Lando Norris and Oscar Piastri.")

assert race_summary_to_text(2025, "Dutch Grand Prix", race, "Circuit Zandvoort in Zandvoort").startswith(
    "The 2025 Dutch Grand Prix at Circuit Zandvoort in Zandvoort was won by")

shared = race.assign(position=[1, 1, 2, 3], grid=[2, 3, 4, 5])
text = race_summary_to_text(1956, "Argentine Grand Prix", shared)
assert "won by Lando Norris for McLaren and Max Verstappen for Red Bull" in text
assert "pole" not in text

print("text_gen checks passed")
