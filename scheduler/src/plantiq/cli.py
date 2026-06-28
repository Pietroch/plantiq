# scheduler/src/plantiq/cli.py

from datetime import date

from sqlalchemy import text

from plantiq.core.database import engine as db_engine


def _load_enum(conn, typename: str) -> list[str]:
    rows = conn.execute(text("""
        SELECT enumlabel::text FROM pg_enum
        JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
        WHERE pg_type.typname = :typename
        ORDER BY enumsortorder
    """), {"typename": typename}).fetchall()
    return [r[0] for r in rows]


def _pick(prompt: str, options: list[str]) -> str:
    print(f"\n{prompt}")
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        raw = input("Choix : ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("Entrée invalide.")


def _load_plants(conn) -> list[dict]:
    rows = conn.execute(text("SELECT id, name FROM plants ORDER BY name")).mappings().fetchall()
    return [dict(r) for r in rows]


def _log_action(conn, plants: list[dict], care_actions: list[str]) -> None:
    plant    = _pick("Plante :", [p["name"] for p in plants])
    plant_id = next(p["id"] for p in plants if p["name"] == plant)
    action   = _pick("Action :", care_actions)

    qty_raw = input("Quantité ml (vide = aucune) : ").strip()
    qty_ml  = int(qty_raw) if qty_raw.isdigit() else None
    note    = input("Note (vide = aucune) : ").strip() or None

    conn.execute(text("""
        INSERT INTO care_logs (plant_id, action, quantity_ml, note)
        VALUES (:plant_id, CAST(:action AS care_action), :qty_ml, :note)
    """), {"plant_id": str(plant_id), "action": action, "qty_ml": qty_ml, "note": note})
    conn.commit()
    print(f"Action '{action}' enregistrée pour {plant}.")


def _snooze(conn, plants: list[dict], notif_types: list[str]) -> None:
    plant      = _pick("Plante :", [p["name"] for p in plants])
    plant_id   = next(p["id"] for p in plants if p["name"] == plant)
    notif_type = _pick("Type de notification :", notif_types)

    date_raw = input("Snooze jusqu'au (JJ/MM/AAAA, vide = indéfini) : ").strip()
    until = None
    if date_raw:
        try:
            d, m, y = date_raw.split("/")
            until = date(int(y), int(m), int(d))
        except Exception:
            print("Format invalide — snooze indéfini.")

    conn.execute(text("""
        INSERT INTO notification_snooze (plant_id, notif_type, snoozed_until)
        VALUES (:plant_id, CAST(:notif_type AS notif_type), :until)
        ON CONFLICT (plant_id, notif_type, done) DO UPDATE SET
            snoozed_at    = NOW(),
            snoozed_until = EXCLUDED.snoozed_until
    """), {"plant_id": str(plant_id), "notif_type": notif_type, "until": until})
    conn.commit()
    label = f"jusqu'au {until}" if until else "indéfiniment"
    print(f"Notification '{notif_type}' snoozée {label} pour {plant}.")


def run() -> None:
    with db_engine.connect() as conn:
        plants       = _load_plants(conn)
        care_actions = _load_enum(conn, "care_action")
        notif_types  = _load_enum(conn, "notif_type")

        if not plants:
            print("Aucune plante trouvée dans la base.")
            return

        while True:
            print("\n1) Logger une action\n2) Snoozer une notification\n3) Quitter")
            choice = input("Choix : ").strip()
            if choice == "1":
                _log_action(conn, plants, care_actions)
            elif choice == "2":
                _snooze(conn, plants, notif_types)
            elif choice == "3":
                break
            else:
                print("Entrée invalide.")


if __name__ == "__main__":
    run()
