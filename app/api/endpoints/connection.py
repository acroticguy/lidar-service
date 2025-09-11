from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from ...models.lidar import (
    LidarConnectionRequest, LidarAutoConnectRequest,
    LidarDiscoveryResponse, OperationResponse, ErrorResponse,
    BerthingModeRequest, BerthingModeResponse
)
from ...services.lidar_manager import lidar_manager
from ...core.logging_config import logger

router = APIRouter(prefix="/connection", tags=["Connection Management"])


@router.post("/discover", response_model=LidarDiscoveryResponse)
async def discover_sensors(computer_ip: Optional[str] = Query(None, description="Computer IP address")):
    """Discover available Livox sensors on the network"""
    try:
        sensors = await lidar_manager.discover_sensors(computer_ip)
        return LidarDiscoveryResponse(sensors=sensors, count=len(sensors))
    except Exception as e:
        logger.error(f"Error discovering sensors: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect/{sensor_id}", response_model=OperationResponse)
async def connect_sensor(sensor_id: str, request: LidarConnectionRequest):
    """Connect to a specific sensor"""
    try:
        success = await lidar_manager.connect_sensor(
            sensor_id=sensor_id,
            computer_ip=request.computer_ip,
            sensor_ip=request.sensor_ip,
            data_port=request.data_port,
            cmd_port=request.cmd_port,
            imu_port=request.imu_port,
            sensor_name=request.sensor_name
        )
        
        if success:
            return OperationResponse(
                success=True,
                message=f"Successfully connected to sensor {sensor_id}",
                data={"sensor_id": sensor_id}
            )
        else:
            raise HTTPException(status_code=400, detail="Failed to connect to sensor")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error connecting to sensor: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto-connect", response_model=OperationResponse)
async def auto_connect_all(request: LidarAutoConnectRequest = LidarAutoConnectRequest()):
    """Auto-connect to all available sensors"""
    try:
        count = await lidar_manager.auto_connect_all(request.computer_ip)
        
        if count > 0:
            return OperationResponse(
                success=True,
                message=f"Successfully connected to {count} sensors",
                data={"connected_count": count}
            )
        else:
            return OperationResponse(
                success=False,
                message="No sensors found or connected",
                data={"connected_count": 0}
            )
            
    except Exception as e:
        logger.error(f"Error in auto-connect: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/disconnect/{sensor_id}", response_model=OperationResponse)
async def disconnect_sensor(sensor_id: str):
    """Disconnect a specific sensor"""
    try:
        success = await lidar_manager.disconnect_sensor(sensor_id, force=True)

        if success:
            return OperationResponse(
                success=True,
                message=f"Successfully disconnected sensor {sensor_id}"
            )
        else:
            raise HTTPException(status_code=404, detail="Sensor not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting sensor: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/disconnect-all", response_model=OperationResponse)
async def disconnect_all_sensors():
    """Disconnect all connected sensors"""
    try:
        sensors = list(lidar_manager.sensors.keys())
        disconnected = 0

        for sensor_id in sensors:
            if await lidar_manager.disconnect_sensor(sensor_id, force=True):
                disconnected += 1

        return OperationResponse(
            success=True,
            message=f"Disconnected {disconnected} sensors",
            data={"disconnected_count": disconnected}
        )

    except Exception as e:
        logger.error(f"Error disconnecting all sensors: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/berthing-mode/on", response_model=BerthingModeResponse)
async def berthing_mode_on(request: BerthingModeRequest):
    """Enable berthing mode for specified sensors - discovers, connects, and starts streaming with center stats"""
    try:
        result = await lidar_manager.enable_berthing_mode(
            sensor_ids=request.sensor_ids,
            computer_ip=request.computer_ip
        )
        
        return BerthingModeResponse(
            berthing_mode_active=result["active"],
            sensor_ids=request.sensor_ids,
            connected_sensors=result["connected_sensors"],
            streaming_sensors=result["streaming_sensors"],
            message=result["message"],
            center_stats=result.get("center_stats"),
            synchronized=result.get("synchronized", False),
            last_sync_timestamp=result.get("last_sync_timestamp"),
            sync_quality=result.get("sync_quality")
        )
        
    except Exception as e:
        logger.error(f"Error enabling berthing mode: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/berthing-mode/off", response_model=BerthingModeResponse)
async def berthing_mode_off(request: BerthingModeRequest):
    """Disable berthing mode for specified sensors - stops streaming, spins down, and disconnects"""
    try:
        result = await lidar_manager.disable_berthing_mode(
            sensor_ids=request.sensor_ids
        )
        
        return BerthingModeResponse(
            berthing_mode_active=result["active"],
            sensor_ids=request.sensor_ids,
            connected_sensors=result["connected_sensors"],
            streaming_sensors=result["streaming_sensors"],
            message=result["message"],
            synchronized=result.get("synchronized", False),
            last_sync_timestamp=result.get("last_sync_timestamp"),
            sync_quality=result.get("sync_quality")
        )
        
    except Exception as e:
        logger.error(f"Error disabling berthing mode: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/berthing-mode/status", response_model=BerthingModeResponse)
async def berthing_mode_status():
    """Get current berthing mode status"""
    try:
        result = await lidar_manager.get_berthing_mode_status()
        
        return BerthingModeResponse(
            berthing_mode_active=result["active"],
            sensor_ids=result["sensor_ids"],
            connected_sensors=result["connected_sensors"],
            streaming_sensors=result["streaming_sensors"],
            message=result["message"],
            center_stats=result.get("center_stats"),
            synchronized=result.get("synchronized", False),
            last_sync_timestamp=result.get("last_sync_timestamp"),
            sync_quality=result.get("sync_quality")
        )
        
    except Exception as e:
        logger.error(f"Error getting berthing mode status: {str(e)}")


@router.post("/connect-fake-lidar", response_model=OperationResponse)
async def connect_fake_lidar():
    """Connect to a fake lidar simulator for testing. Each call creates a different fake lidar."""
    try:
        success, sensor_id = await lidar_manager.connect_fake_lidar(
            sensor_id=None,  # Let the manager generate a unique ID
            computer_ip="127.0.0.1",
            sensor_ip="127.0.0.1",
            data_port=None,  # Let the manager find available ports
            cmd_port=None,
            imu_port=None
        )

        if success:
            return OperationResponse(
                success=True,
                message=f"Successfully connected to fake lidar simulator {sensor_id}",
                data={"sensor_id": sensor_id, "is_simulation": True}
            )
        else:
            raise HTTPException(status_code=400, detail=f"Failed to connect to fake lidar {sensor_id}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error connecting to fake lidar: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))