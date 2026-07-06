import logging
logging.basicConfig(level=logging.INFO)
from utils.database import SessionLocal
from services.cdc_monitoring import CdcMonitoringService

db = SessionLocal()
service = CdcMonitoringService(db)
metrics = service.fetch_realtime_datastream_metrics()
print("METRICS:", metrics)
