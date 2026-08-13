import logging
from app.database import SessionLocal, engine, Base
from app.models import Unit
from app.schemas import EmergencyType, UnitStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gotham_dispatch.seed")


DEFAULT_UNITS = [
    {"call_sign": "FIRE-01", "type": EmergencyType.FIRE.value, "latitude": 40.7128, "longitude": -74.0060},
    {"call_sign": "FIRE-02", "type": EmergencyType.FIRE.value, "latitude": 40.7200, "longitude": -74.0100},
    {"call_sign": "POLICE-01", "type": EmergencyType.POLICE.value, "latitude": 40.7300, "longitude": -73.9900},
    {"call_sign": "POLICE-02", "type": EmergencyType.POLICE.value, "latitude": 40.7400, "longitude": -73.9800},
    {"call_sign": "MED-01", "type": EmergencyType.MEDICAL.value, "latitude": 40.7150, "longitude": -74.0050},
    {"call_sign": "MED-02", "type": EmergencyType.MEDICAL.value, "latitude": 40.7250, "longitude": -73.9950},
]


def seed_database():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        created_count = 0
        for unit_data in DEFAULT_UNITS:
            existing = db.query(Unit).filter(Unit.call_sign == unit_data["call_sign"]).first()
            if not existing:
                unit = Unit(
                    call_sign=unit_data["call_sign"],
                    type=unit_data["type"],
                    latitude=unit_data["latitude"],
                    longitude=unit_data["longitude"],
                    status=UnitStatus.AVAILABLE.value
                )
                db.add(unit)
                created_count += 1
        db.commit()
        logger.info(f"Seeding completed successfully. Added {created_count} units.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error during database seeding: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
