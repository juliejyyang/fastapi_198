import serial

connection = None

# connect to arduino
def connect_arduino(port='/dev/cu.usbmodem2101', baudrate=9600):
    global connection
    # troubleshooting
    try:
        connection = serial.Serial(port=port, baudrate=baudrate, timeout=1)
        print(f"Connected to Arduino on {port}")
    except Exception as e:
        print(f"Failed to connect: {e}")

# read one temperature from arduino
def read_temperature():
    if connection:
        try:
            connection.timeout = 1  # 1 second timeout
            if connection.in_waiting:
                line = connection.readline().decode('utf-8').strip()
                return line
        except Exception as e:
            print(f"Error reading from Arduino: {e}")
            return None
    return None

# close connection
def close_arduino():
    global connection
    if connection and connection.is_open:
        connection.close()