# scheduler/tests/test_simulation.py

import os
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))  # ensure tests/ is on path

from engine_dry import run_dry

# ── Plant fixtures ────────────────────────────────────────────────────────────

PLANT_FIXTURES = [
    {
        "id": "sim-001",
        "name": "Cactus",
        "species": "Opuntia microdasys",
        "profile": {
            "watering_frequency_days_summer": 14,
            "watering_frequency_days_winter": 30,
            "watering_amount": "light",
            "watering_mode": "soil_only",
            "watering_quantity_ml": None,
            "watering_instructions": "Arroser uniquement quand la terre est complètement sèche. Ne jamais mouiller les coussinets.",
            "humidity_level": "low",
            "temp_min_c": 5.0,
            "temp_max_c": 45.0,
            "fertilizing_frequency_days": 60,
            "repotting_frequency_months": 24,
            "toxic_to_pets": False,
            "difficulty_level": "easy",
        },
    },
    {
        "id": "sim-002",
        "name": "Rose",
        "species": "Rosa hybride",
        "profile": {
            "watering_frequency_days_summer": 3,
            "watering_frequency_days_winter": 7,
            "watering_amount": "heavy",
            "watering_mode": "soil_only",
            "watering_quantity_ml": None,
            "watering_instructions": "Arroser au pied uniquement — jamais sur les feuilles pour éviter la maladie des taches noires.",
            "humidity_level": "medium",
            "temp_min_c": -5.0,
            "temp_max_c": 35.0,
            "fertilizing_frequency_days": 14,
            "repotting_frequency_months": 12,
            "toxic_to_pets": True,
            "difficulty_level": "hard",
        },
    },
    {
        "id": "sim-003",
        "name": "Fougère de Boston",
        "species": "Nephrolepis exaltata",
        "profile": {
            "watering_frequency_days_summer": 3,
            "watering_frequency_days_winter": 5,
            "watering_amount": "moderate",
            "watering_mode": "mixed",
            "watering_quantity_ml": None,
            "watering_instructions": "Arroser la terre et brumiser les frondes quotidiennement en été. Éviter les courants d'air.",
            "humidity_level": "high",
            "temp_min_c": 10.0,
            "temp_max_c": 28.0,
            "fertilizing_frequency_days": 30,
            "repotting_frequency_months": 18,
            "toxic_to_pets": False,
            "difficulty_level": "medium",
        },
    },
    {
        "id": "sim-004",
        "name": "Yucca",
        "species": "Yucca elephantipes",
        "profile": {
            "watering_frequency_days_summer": 14,
            "watering_frequency_days_winter": 21,
            "watering_amount": "moderate",
            "watering_mode": "soil_only",
            "watering_quantity_ml": None,
            "watering_instructions": "Arroser abondamment puis laisser sécher complètement. Ne pas mouiller le tronc.",
            "humidity_level": "low",
            "temp_min_c": 7.0,
            "temp_max_c": 35.0,
            "fertilizing_frequency_days": 30,
            "repotting_frequency_months": 24,
            "toxic_to_pets": True,
            "difficulty_level": "easy",
        },
    },
    {
        "id": "sim-005",
        "name": "Dionée",
        "species": "Dionaea muscipula",
        "profile": {
            "watering_frequency_days_summer": 3,
            "watering_frequency_days_winter": 14,
            "watering_amount": "heavy",
            "watering_mode": "misting",
            "watering_quantity_ml": None,
            "watering_instructions": "Arroser par immersion uniquement avec de l'eau distillée ou de pluie. Jamais d'eau du robinet — le calcaire tue la plante.",
            "humidity_level": "high",
            "temp_min_c": 0.0,
            "temp_max_c": 35.0,
            "fertilizing_frequency_days": None,
            "repotting_frequency_months": 12,
            "toxic_to_pets": False,
            "difficulty_level": "hard",
        },
    },
    {
        "id": "sim-006",
        "name": "Orchidée Phalaenopsis",
        "species": "Phalaenopsis amabilis",
        "profile": {
            "watering_frequency_days_summer": 7,
            "watering_frequency_days_winter": 10,
            "watering_amount": "moderate",
            "watering_mode": "soil_only",
            "watering_quantity_ml": None,
            "watering_instructions": "Arroser par immersion 15 minutes, puis égoutter complètement. Ne jamais laisser d'eau dans le cache-pot. Ne pas mouiller le cœur de la plante.",
            "humidity_level": "high",
            "temp_min_c": 15.0,
            "temp_max_c": 30.0,
            "fertilizing_frequency_days": 14,
            "repotting_frequency_months": 24,
            "toxic_to_pets": False,
            "difficulty_level": "medium",
        },
    },
]

# ── Random context generation ─────────────────────────────────────────────────

STATUSES    = ["healthy", "sick", "recovering", "burned", "dormant", "dying"]
ISSUE_TYPES = ["overwatering", "underwatering", "pest", "disease", "sunburn", "rootbound", "none"]
SOIL_CONDS  = ["correct", "exhausted", "moldy", "compacted", "waterlogged"]
POT_TYPES   = ["plastic", "terracotta", "ceramic", "fabric"]
LIGHT_TYPES = ["direct", "indirect", "artificial", "none"]
CONDITIONS  = ["sunny", "cloudy", "rainy", "stormy", "snowy"]
DISTANCES   = ["very_close", "close", "medium", "far"]


def random_context(plant_id: str, today: date) -> dict:
    status     = random.choice(STATUSES)
    issue_type = "none" if status == "healthy" else random.choice([i for i in ISSUE_TYPES if i != "none"])
    pot_type     = random.choice(POT_TYPES)
    pot_diameter = random.choice([12, 15, 17, 20, 24, 28, 32])
    pot_height   = random.choice([10, 12, 15, 18, 20, 25, 30])
    last_water = today - timedelta(days=random.randint(0, 30))
    last_repot = today - timedelta(days=random.randint(30, 730))
    temp_max   = round(random.uniform(5, 40), 1)
    temp_min   = round(temp_max - random.uniform(5, 15), 1)
    humidity   = random.randint(20, 95)
    condition  = random.choice(CONDITIONS)
    is_indoor  = random.choice([True, True, True, False])
    has_drain  = random.choice([True, True, False])
    near_ac    = random.choice([True, False, False])
    near_heat  = random.choice([True, False, False])
    shade      = random.choice([True, False, False])
    has_clay   = random.choice([True, False])

    # Physical constraints
    if condition == "snowy":
        temp_max = min(temp_max, 2.9)
        temp_min = min(temp_min, temp_max - 1)
    if is_indoor:
        temp_min = max(temp_min, 5.1)

    return {
        "plant_location": {
            "indoor": is_indoor,
            "shade": shade,
            "near_ac": near_ac,
            "near_heating": near_heat,
            "light_type": random.choice(LIGHT_TYPES),
            "distance_to_window": random.choice(DISTANCES),
        },
        "container": {
            "pot_type": pot_type,
            "pot_diameter_cm": pot_diameter,
            "pot_height_cm": pot_height,
            "has_drainage": has_drain,
            "soil_condition": random.choice(SOIL_CONDS),
            "soil_issues": random.choice([None, None, "mold, calcium_deposits", None]),
            "last_repotted": last_repot,
            "repotting_urgent": random.choice([False, False, False, True]),
            "repotting_notes": "Vérifier les racines." if random.random() > 0.7 else None,
        },
        "health": {
            "status": status,
            "issue_type": issue_type,
            "treating ": "En cours de traitement." if status in ("sick", "recovering") else None,
            "resolved_at": None,
        },
        "care_logs": {
            "watering":    {"done_at": last_water},
            "fertilizing": {"done_at": today - timedelta(days=random.randint(0, 60))},
            "misting":     {"done_at": today - timedelta(days=random.randint(0, 10))},
        },
        "weather": {
            "temperature_max": temp_max,
            "temperature_min": temp_min,
            "humidity": humidity,
            "condition": condition,
            "wind_speed": round(random.uniform(0, 50), 1),
        },
        "accessories": [
            {
                "type": "cachepot",
                "has_clay_pebbles": has_clay,
            }
        ],
    }


# ── Report generation ─────────────────────────────────────────────────────────

def generate_report(results: list[dict], output_path: str, seed: int) -> None:
    lines = [
        "# Plantiq — Simulation Report",
        "",
        f"> **Date:** {date.today()}  ",
        f"> **Random seed:** {seed}  ",
        f"> **Plants tested:** {len(results)}",
        "",
        "---",
        "",
    ]

    for r in results:
        plant  = r["plant"]
        ctx    = r["context"]
        notifs = r["notifications"]
        w      = ctx["weather"]
        h      = ctx["health"]
        c      = ctx["container"]
        pl     = ctx["plant_location"]

        lines += [
            f"## {plant['name']} — {plant['species']}",
            "",
            "### Context",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Status | `{h['status']}` |",
            f"| Issue | `{h['issue_type']}` |",
            f"| Indoor | `{pl['indoor']}` |",
            f"| Shade | `{pl['shade']}` |",
            f"| Near AC | `{pl['near_ac']}` |",
            f"| Near heating | `{pl['near_heating']}` |",
            f"| Pot | `{c['pot_type']}` ⌀{c['pot_diameter_cm']}cm × h{c['pot_height_cm']}cm — drainage: `{c['has_drainage']}` |",
            f"| Soil condition | `{c['soil_condition']}` |",
            f"| Soil issues | `{c['soil_issues'] or 'none'}` |",
            f"| Last watered | `{ctx['care_logs']['watering']['done_at']}` |",
            f"| Last repotted | `{c['last_repotted']}` |",
            f"| Repotting urgent | `{c['repotting_urgent']}` |",
            f"| Temp min/max | `{w['temperature_min']}°C / {w['temperature_max']}°C` |",
            f"| Humidity | `{w['humidity']}%` |",
            f"| Condition | `{w['condition']}` |",
            "",
            "### Notifications generated",
            "",
        ]

        if notifs:
            for n in notifs:
                lines += [
                    f"#### {n['title']}",
                    "",
                    "```",
                    n["body"],
                    "```",
                    "",
                ]
        else:
            lines.append("_No notifications triggered._")
            lines.append("")

        lines.append("---")
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ── Entry point ───────────────────────────────────────────────────────────────

def run_simulation(seed: int | None = None) -> str:
    if seed is None:
        seed = random.randint(0, 99999)
    random.seed(seed)

    today = date.today()
    results = []

    for fixture in PLANT_FIXTURES:
        ctx = random_context(fixture["id"], today)
        plant = {
            "id": fixture["id"],
            "name": fixture["name"],
            "species": fixture["species"],
            "city": "Meise (simulation)",
        }
        notifs = run_dry(
            plant=plant,
            profile=fixture["profile"],
            plant_location=ctx["plant_location"],
            container=ctx["container"],
            accessories=ctx["accessories"],
            health=ctx["health"],
            care_logs=ctx["care_logs"],
            weather=ctx["weather"],
        )
        results.append({"plant": plant, "context": ctx, "notifications": notifs})

    output_path = "tests/simulation_report.md"
    generate_report(results, output_path, seed)
    print(f"Report generated: {output_path} (seed={seed})")
    return output_path


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run_simulation(seed)
