import socket
import struct
import threading
import time
import random
import math
from typing import Optional
from ..core.logging_config import logger

class FakeLidarSimulator:
    """Simulates a Livox lidar for testing purposes"""

    def __init__(self, showMessages=False):
        self.is_simulation = True
        self._isConnected = False
        self._isData = False
        self._sensorIP = ""
        self._dataPort = -1
        self._cmdPort = -1
        self._computerIP = ""
        self._deviceType = "Fake-Lidar"
        self._serial = "SIM0001"
        self._firmware = "01.00.00"
        self._showMessages = showMessages
        self._dataSocket = None
        self._cmdSocket = None
        self._data_thread = None
        self._running = False
        self._command_thread = None
        self._command_running = False

    def connect(self, computerIP, sensorIP, dataPort, cmdPort, imuPort=None, sensor_name_override=""):
        """Simulate connection to fake lidar"""
        self._computerIP = computerIP
        self._sensorIP = sensorIP
        self._dataPort = dataPort
        self._cmdPort = cmdPort

        # Create UDP sockets
        self._dataSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._cmdSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Bind sockets
        try:
            self._dataSocket.bind((computerIP, dataPort))
            # For fake lidar, use standard command port 65000 like real sensors
            self._cmdSocket.bind((computerIP, 65000))
            self._isConnected = True

            # Start command listening thread
            self._command_running = True
            self._command_thread = threading.Thread(target=self._command_listener, daemon=True)
            self._command_thread.start()

            if self._showMessages:
                logger.info(f"Connected to Fake Lidar at {sensorIP}")
            return 1  # Success
        except Exception as e:
            if self._showMessages:
                logger.error(f"Failed to connect Fake Lidar: {e}")
            return 0

    def disconnect(self):
        """Disconnect from fake lidar"""
        self._running = False
        self._command_running = False
        if self._data_thread:
            self._data_thread.join(timeout=1.0)
        if self._command_thread:
            self._command_thread.join(timeout=1.0)
        if self._dataSocket:
            self._dataSocket.close()
        if self._cmdSocket:
            self._cmdSocket.close()
        self._isConnected = False
        self._isData = False
        if self._showMessages:
            logger.info("Disconnected from Fake Lidar")

    def lidarSpinUp(self):
        """Simulate spinning up the lidar"""
        if self._showMessages:
            logger.info("Fake Lidar: Spinning up...")
        time.sleep(0.1)  # Simulate spin up time
        if self._showMessages:
            logger.info("Fake Lidar: Ready")

    def lidarSpinDown(self):
        """Simulate spinning down the lidar"""
        if self._showMessages:
            logger.info("Fake Lidar: Spinning down...")
        time.sleep(0.1)
        if self._showMessages:
            logger.info("Fake Lidar: Stopped")

    def dataStart_RT_B(self):
        """Start fake data streaming"""
        if not self._isConnected:
            return

        self._isData = True
        self._running = True
        self._data_thread = threading.Thread(target=self._generate_fake_data, daemon=True)
        self._data_thread.start()

        if self._showMessages:
            logger.info("Fake Lidar: Started data streaming")

    # Add command constants that openpylivox uses
    _CMD_DATA_START = b'\xaa\x01\x14\x00\x00\x00\x00\xb5\xed\x01\x01'  # Simplified command
    _CMD_DATA_STOP = b'\xaa\x01\x14\x00\x00\x00\x00\xb5\xed\x01\x00'   # Simplified command

    def dataStop(self):
        """Stop fake data streaming"""
        self._isData = False
        self._running = False
        if self._data_thread:
            self._data_thread.join(timeout=1.0)

        if self._showMessages:
            logger.info("Fake Lidar: Stopped data streaming")

    def _generate_fake_data(self):
        """Generate and send fake lidar data packets"""
        packet_count = 0

        while self._running and self._isData:
            try:
                # Create fake packet (version 5, Cartesian single return)
                packet = self._create_fake_packet(packet_count)
                # Send to the computer IP since that's where the socket is bound
                target_addr = (self._computerIP, self._dataPort)
                self._dataSocket.sendto(packet, target_addr)
                packet_count += 1
                time.sleep(0.01)  # ~100Hz

            except Exception as e:
                if self._showMessages:
                    logger.info(f"Fake Lidar: Error sending data: {e}")
                break

    def _create_fake_packet(self, packet_count: int) -> bytes:
        """Create a fake Livox data packet"""
        # Packet header (18 bytes)
        version = 5
        slot_id = 0
        lidar_id = 0
        reserved = 0
        status_code = 0  # Normal status
        timestamp_type = 0  # Nanoseconds
        data_type = 0  # Cartesian single return
        timestamp = int(time.time() * 1_000_000_000)  # Nanoseconds since epoch

        header = struct.pack('<BBBBLBBQ',
                           version, slot_id, lidar_id, reserved,
                           status_code, timestamp_type, data_type, timestamp)

        # Generate 100 fake points
        points_data = b''
        for i in range(100):
            # Generate fake point data
            x, y, z, intensity = self._generate_fake_point(i, packet_count)

            # Pack point data (13 bytes each)
            point_data = struct.pack('<iiiB', x, y, z, intensity)
            points_data += point_data

        return header + points_data

    def _generate_fake_point(self, point_idx: int, packet_count: int) -> tuple:
        """Generate a fake 3D point with intensity"""
        # Create some fake objects in the scene
        angle = (point_idx / 100.0) * 2 * math.pi  # Full circle
        distance = 5.0 + random.uniform(-2.0, 3.0)  # 3-8m range

        # Add some variation for multiple objects
        if packet_count % 10 == 0:  # Every 10 packets, create a closer object
            distance = 2.0 + random.uniform(-0.5, 1.0)

        x = int(distance * 1000)  # mm

        # Generate points concentrated around center for berthing measurements
        # Most points should be within 9cm radial distance for center beam detection
        if point_idx < 50:  # First 50 points are center beam
            radial_distance = random.uniform(0, 0.09)  # Within 9cm for center beam
            angle_offset = random.uniform(0, 2 * math.pi)
            y = int(radial_distance * math.cos(angle_offset) * 1000)
            z = int(radial_distance * math.sin(angle_offset) * 1000)
            intensity = random.randint(200, 255)  # High intensity for center beam
        else:  # Other points are more spread out
            y = int(random.uniform(-0.5, 0.5) * 1000)
            z = int(random.uniform(-0.5, 0.5) * 1000)
            intensity = random.randint(10, 150)  # Lower intensity for peripheral points

        return x, y, z, intensity

    def _command_listener(self):
        """Listen for incoming commands and respond appropriately"""
        while self._command_running:
            try:
                # Listen for commands with timeout
                self._cmdSocket.settimeout(0.1)
                data, addr = self._cmdSocket.recvfrom(1024)

                # Check if this is a data start command
                if len(data) >= 11 and data[:11] == self._CMD_DATA_START[:11]:
                    if self._showMessages:
                        logger.info("Fake Lidar: Received data start command")
                    self.dataStart_RT_B()

                # Check if this is a data stop command
                elif len(data) >= 11 and data[:11] == self._CMD_DATA_STOP[:11]:
                    if self._showMessages:
                        logger.info("Fake Lidar: Received data stop command")
                    self.dataStop()

            except socket.timeout:
                continue
            except Exception as e:
                if self._command_running:  # Only log if not shutting down
                    if self._showMessages:
                        logger.error(f"Fake Lidar: Command listener error: {e}")
                break

    def serialNumber(self) -> str:
        """Return fake serial number"""
        return self._serial

    def firmware(self) -> str:
        """Return fake firmware version"""
        return self._firmware

    def connectionParameters(self):
        """Return connection parameters"""
        return [self._computerIP, self._sensorIP, self._dataPort, 65000]  # Use standard cmd port

    def setCartesianCS(self):
        """Set coordinate system (no-op for fake)"""
        pass

    def lidarStatusCodes(self):
        """Return fake status codes"""
        return [0, 0, 0, 0, 0, 0, 0, 0]  # All normal

    def extrinsicParameters(self):
        """Return fake extrinsic parameters"""
        return [0.0, 0.0, 2.0, 0.0, 0.0, 0.0]  # Default position

    def setExtrinsicTo(self, x, y, z, roll, pitch, yaw):
        """Set extrinsic parameters (no-op for fake)"""
        pass

    def showMessages(self, show: bool):
        """Set message display"""
        self._showMessages = show