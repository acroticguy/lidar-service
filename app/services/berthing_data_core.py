from .lidar_manager import lidar_manager
from ..core.logging_config import logger
from typing import Dict, Any
import time

async def fetch_berthing_data_for_sensor(sensor_id: str) -> Dict[str, Any]:
    """
    Retrieves raw berthing data for a specific sensor.
    """
    if sensor_id not in lidar_manager.sensors:
        logger.warning(f"Sensor {sensor_id} not found when fetching core data.")
        return {"sensor_id": sensor_id, "status": "not_found", "message": f"Sensor {sensor_id} not found."}
    
    if not lidar_manager.stream_active.get(sensor_id, False):
        logger.warning(f"Data stream not active for sensor {sensor_id}.")
        return {"sensor_id": sensor_id, "status": "stream_inactive", "message": f"Data stream not active for sensor {sensor_id}."}
    
    sync_data = lidar_manager.sensor_sync_data.get(sensor_id, {})
    center_stats = sync_data.get("center_stats", {})
    
    # Extract essential data
    timestamp = sync_data.get("timestamp", 0)
    distance = center_stats.get("stable_distance", 0.0)
    speed = center_stats.get("speed_mps", 0.0)
    speed_mm_s = center_stats.get("speed_mm_s", 0.0)
    instant_speed = center_stats.get("instant_speed", 0.0)
    sa_averaged_speed = center_stats.get("sa_averaged_speed", 0.0)
    trend_speed = center_stats.get("trend_speed", 0.0)
    speed_precision_mm_s = center_stats.get("speed_precision_mm_s", 0.0)
    is_moving = center_stats.get("is_vessel_moving", False)
    movement_phase = center_stats.get("movement_phase", "unknown")
    confidence = center_stats.get("speed_confidence", 0.0)
    
    # Determine movement direction
    if is_moving:
        if speed < 0:
            direction = "approaching"
        elif speed > 0:
            direction = "departing"
        else:
            direction = "lateral"
    else:
        direction = "stationary"
    
    return {
        "sensor_id": sensor_id,
        "timestamp": timestamp,
        "distance": round(distance, 3),
        "distance_mm": round(distance * 1000, 0),
        "speed": round(speed, 4),
        "speed_mm_s": round(speed_mm_s, 1),
        "instant_speed": round(instant_speed, 4),
        "instant_speed_mm_s": round(instant_speed * 1000, 1),
        "sa_averaged_speed": round(sa_averaged_speed, 4),
        "sa_averaged_speed_mm_s": round(sa_averaged_speed * 1000, 1),
        "trend_speed": round(trend_speed, 4),
        "speed_precision_mm_s": round(speed_precision_mm_s, 3),
        "is_moving": is_moving,
        "direction": direction,
        "movement_phase": movement_phase,
        "confidence": round(confidence, 2),
        "stable_distance": round(distance, 3),
        "status": "active"
    }
    
async def get_all_berthing_data_core() -> Dict[str, Any]:
    """
    Get berthing data for all active sensors from the core logic.
    This function will be used by both the HTTP endpoint and the WebSocket emitter.
    """
    result = {}
    
    for sensor_id in lidar_manager.berthing_mode_sensors:
        if lidar_manager.stream_active.get(sensor_id, False):
            try:
                # Reuse the individual sensor data fetching logic
                sensor_data = await fetch_berthing_data_for_sensor(sensor_id)
                result[sensor_id] = sensor_data
            except Exception as e:
                logger.error(f"Error fetching core berthing data for sensor {sensor_id}: {e}")
                result[sensor_id] = {
                    "sensor_id": sensor_id,
                    "status": "error",
                    "message": str(e)
                }
    
    return {
        "sensors": result,
        "count": len(result),
        "berthing_mode_active": lidar_manager.berthing_mode_active,
        "synchronized": lidar_manager.sync_coordinator_active,
        "_server_timestamp_utc": time.time() # Add server timestamp here for consistency
    }