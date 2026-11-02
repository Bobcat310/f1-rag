"""Checks for the sentence templates. Run: python tests/test_text_gen.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.text_gen import constructor_standing_to_text, race_summary_to_text, result_to_text, standing_to_text

result = {"season": 2021, "race_name": "Abu Dhabi Grand Prix", "driver_name": "Max Verstappen", "position": 1,
          "grid": 1, "status": "Finished", "points": 25.0, "constructor": "Red Bull", "fastest_lap_rank": 2}
assert result_to_text(result) == ("In the 2021 Abu Dhabi Grand Prix, Max Verstappen finished 1st (winner) "
                                  "starting from position 1, scoring 25.0 points for Red Bull.")

driver = {"season": 2026, "position": 2, "points": 63.0, "wins": 1, "driver_id": "russell", "constructor": "Mercedes"}
assert standing_to_text(driver) == ("At the end of the 2026 season, russell was 2nd in the drivers championship "
                                    "with 63.0 points and 1 wins, driving for Mercedes.")
assert standing_to_text(driver, after_round=18).startswith("After round 18 of the 2026 season, russell was 2nd")
assert standing_to_text({**driver, "position": None}) is None

team = {"season": 2026, "position": 1, "points": 100.0, "wins": 3, "constructor": "Mercedes"}
assert constructor_standing_to_text(team) == "In the 2026 constructors championship, Mercedes finished 1st with 100.0 points and 3 wins."
assert "finished" not in constructor_standing_to_text(team, after_round=18)

race = pd.DataFrame([
    {"driver_name": "Lando Norris", "constructor": "McLaren", "position": 2, "grid": 1},
    {"driver_name": "Max Verstappen", "constructor": "Red Bull", "position": 1, "grid": 3},
    {"driver_name": "Oscar Piastri", "constructor": "McLaren", "position": 3, "grid": 2},
    {"driver_name": "George Russell", "constructor": "Mercedes", "position": 4, "grid": 4},
])
assert race_summary_to_text(2025, "Dutch Grand Prix", race) == (
    "The 2025 Dutch Grand Prix was won by Max Verstappen for Red Bull, with Lando Norris on pole position, "
    "and the podium was Max Verstappen, Lando Norris and Oscar Piastri.")

shared = race.assign(position=[1, 1, 2, 3], grid=[2, 3, 4, 5])
text = race_summary_to_text(1956, "Argentine Grand Prix", shared)
assert "won by Lando Norris for McLaren and Max Verstappen for Red Bull" in text
assert "pole" not in text

print("text_gen checks passed")
