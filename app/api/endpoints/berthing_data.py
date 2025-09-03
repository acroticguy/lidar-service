"""
Simplified berthing data endpoint for point cloud viewer
Provides essential distance and speed measurements
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional

from ...services.berthing_data_core import fetch_berthing_data_for_sensor
from ...services.lidar_manager import lidar_manager
from ...core.logging_config import logger
from ...services.db_streamer_service import db_streamer_service
from ...models.lidar import OperationResponse

router = APIRouter()


@router.get("/sensor/{sensor_id}", response_model=Dict[str, Any])
async def get_berthing_data(sensor_id: str) -> Dict[str, Any]:
    """
    Get simplified berthing data for point cloud viewer
    
    Returns essential measurements:
    - Synchronized timestamp
    - Distance to vessel
    - Speed (approach/departure)
    - Movement status
    """
    
    try:
        # berthing_data_core handles validation and data extraction
        raw_data = await fetch_berthing_data_for_sensor(sensor_id)
        
        if raw_data.get("status") == "not_found":
            raise HTTPException(status_code=404, detail=raw_data["message"])
        if raw_data.get("status") == "stream_inactive":
            raise HTTPException(status_code=400, detail=raw_data["message"])
        
        return raw_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting berthing data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all", response_model=Dict[str, Any])
async def get_all_berthing_data() -> Dict[str, Any]:
    """
    Get berthing data for all active sensors
    
    Returns a dictionary with sensor IDs as keys
    """
    try:
        result = {}
        
        for sensor_id in lidar_manager.berthing_mode_sensors:
            if lidar_manager.stream_active.get(sensor_id, False):
                try:
                    sensor_data = await get_berthing_data(sensor_id)
                    result[sensor_id] = sensor_data
                except:
                    result[sensor_id] = {
                        "sensor_id": sensor_id,
                        "status": "error"
                    }
        
        return {
            "sensors": result,
            "count": len(result),
            "berthing_mode_active": lidar_manager.berthing_mode_active,
            "synchronized": lidar_manager.sync_coordinator_active
        }
        
    except Exception as e:
        logger.error(f"Error getting all berthing data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{sensor_id}", response_model=Dict[str, Any])
async def get_berthing_history(
    sensor_id: str,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get historical berthing data for a sensor
    
    Args:
        sensor_id: Sensor identifier
        limit: Maximum number of historical points to return
        
    Returns:
        Historical distance and speed measurements
    """
    try:
        # Check if sensor has vessel speed calculator
        if sensor_id not in lidar_manager.vessel_speed_calculators:
            raise HTTPException(
                status_code=404,
                detail=f"No speed calculator found for sensor {sensor_id}"
            )
        
        calculator = lidar_manager.vessel_speed_calculators[sensor_id]
        
        # Get distance history
        history = list(calculator.distance_history)
        
        # Limit the results
        if len(history) > limit:
            history = history[-limit:]
        
        # Format history data
        history_data = []
        for i, (timestamp, distance) in enumerate(history):
            # Calculate speed between points
            if i > 0:
                prev_t, prev_d = history[i-1]
                dt = timestamp - prev_t
                if dt > 0:
                    speed = (distance - prev_d) / dt
                else:
                    speed = 0.0
            else:
                speed = 0.0
            
            history_data.append({
                "timestamp": timestamp,
                "distance": round(distance, 3),
                "speed": round(speed, 4),
                "speed_mm_s": round(speed * 1000, 1)
            })
        
        return {
            "sensor_id": sensor_id,
            "history": history_data,
            "count": len(history_data),
            "oldest_timestamp": history_data[0]["timestamp"] if history_data else 0,
            "latest_timestamp": history_data[-1]["timestamp"] if history_data else 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting berthing history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary", response_model=Dict[str, Any])
async def get_berthing_summary() -> Dict[str, Any]:
    """
    Get summary of berthing operation status
    
    Provides high-level overview for monitoring displays
    """
    try:
        summary = {
            "berthing_mode_active": lidar_manager.berthing_mode_active,
            "sensors": {},
            "overall_status": "idle"
        }
        
        any_moving = False
        min_distance = float('inf')
        max_speed = 0.0
        
        for sensor_id in lidar_manager.berthing_mode_sensors:
            if sensor_id in lidar_manager.berthing_mode_center_stats:
                stats = lidar_manager.berthing_mode_center_stats[sensor_id]
                
                distance = stats.get("stable_distance", 0.0)
                speed = abs(stats.get("speed_mps", 0.0))
                is_moving = stats.get("is_vessel_moving", False)
                phase = stats.get("movement_phase", "unknown")
                
                summary["sensors"][sensor_id] = {
                    "distance": round(distance, 3),
                    "speed_mm_s": round(speed * 1000, 1),
                    "is_moving": is_moving,
                    "phase": phase
                }
                
                if is_moving:
                    any_moving = True
                if distance < min_distance and distance > 0:
                    min_distance = distance
                if speed > max_speed:
                    max_speed = speed
        
        # Determine overall status
        if not lidar_manager.berthing_mode_active:
            summary["overall_status"] = "inactive"
        elif any_moving:
            if min_distance < 5.0:
                summary["overall_status"] = "final_approach"
            elif min_distance < 20.0:
                summary["overall_status"] = "approaching"
            else:
                summary["overall_status"] = "monitoring"
        else:
            if min_distance < 1.0:
                summary["overall_status"] = "berthed"
            else:
                summary["overall_status"] = "standby"
        
        summary["min_distance"] = round(min_distance, 3) if min_distance != float('inf') else None
        summary["max_speed_mm_s"] = round(max_speed * 1000, 1)
        
        return summary
        
    except Exception as e:
        logger.error(f"Error getting berthing summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream/on", response_model=OperationResponse)
async def start_db_streaming_endpoint():
    """
    Starts the database streaming process.
    """
    try:
        await db_streamer_service.start_db_streaming()
        return OperationResponse(success=True, message="Database streaming initiated.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting DB streaming: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start DB streaming: {e}")


@router.post("/stream/off", response_model=OperationResponse)
async def stop_db_streaming_endpoint():
    """
    Stops the database streaming process.
    """
    try:
        await db_streamer_service.stop_db_streaming()
        return OperationResponse(success=True, message="Database streaming stopped.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping DB streaming: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to stop DB streaming: {e}")


@router.post("/berth/{berth_id}/activate", response_model=Dict[str, Any])
async def activate_berthing_by_berth(berth_id: int, computer_ip: Optional[str] = None, auto_update: bool = False):
    """
    Activate berthing mode for all lasers associated with a specific berth.

    This endpoint:
    1. Queries the database to find all lasers for the berth
    2. Enables berthing mode for those lasers
    3. Starts database consumer if auto_update is True

    Args:
        berth_id: The berth ID to activate berthing for
        computer_ip: Optional computer IP for sensor discovery
        auto_update: Whether to start the database consumer for automatic data streaming

    Returns:
        Dictionary with activation results including:
        - success: Whether activation was successful
        - berth_id: The berth ID that was processed
        - lasers_found: List of lasers associated with the berth
        - sensor_ids: List of sensor IDs that were activated
        - berthing_result: Detailed berthing mode activation results
        - db_consumer_started: Whether database consumer was started
    """
    try:
        logger.info(f"Activating berthing mode for berth {berth_id}")

        result = await lidar_manager.enable_berthing_by_berth(berth_id, computer_ip, auto_update)

        if result.get("success"):
            logger.info(f"Successfully activated berthing mode for berth {berth_id}")
            return result
        else:
            logger.warning(f"Failed to activate berthing mode for berth {berth_id}: {result.get('message')}")
            raise HTTPException(
                status_code=400,
                detail=result.get("message", f"Failed to activate berthing for berth {berth_id}")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating berthing for berth {berth_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error activating berthing for berth {berth_id}: {str(e)}"
        )


@router.post("/berth/{berth_id}/deactivate", response_model=Dict[str, Any])
async def deactivate_berthing_by_berth(berth_id: int):
    """
    Deactivate berthing mode for all lasers associated with a specific berth.

    This endpoint:
    1. Queries the database to find all lasers for the berth
    2. Disables berthing mode for those lasers
    3. Stops database streaming if it was started for this berth

    Args:
        berth_id: The berth ID to deactivate berthing for

    Returns:
        Dictionary with deactivation results including:
        - success: Whether deactivation was successful
        - berth_id: The berth ID that was processed
        - lasers_found: List of lasers associated with the berth
        - sensor_ids: List of sensor IDs that were deactivated
        - berthing_result: Detailed berthing mode deactivation results
        - db_streaming_stopped: Whether database streaming was stopped
    """
    try:
        logger.info(f"Deactivating berthing mode for berth {berth_id}")

        result = await lidar_manager.disable_berthing_by_berth(berth_id)

        if result.get("success"):
            logger.info(f"Successfully deactivated berthing mode for berth {berth_id}")
            return result
        else:
            logger.warning(f"Failed to deactivate berthing mode for berth {berth_id}: {result.get('message')}")
            raise HTTPException(
                status_code=400,
                detail=result.get("message", f"Failed to deactivate berthing for berth {berth_id}")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating berthing for berth {berth_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error deactivating berthing for berth {berth_id}: {str(e)}"
        )