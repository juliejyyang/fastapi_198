import serial

connection = None

# connect to arduino
def connect_arduino(port='/dev/cu.usbmodem101', baudrate=9600):
    global connection
    try:
        connection = serial.Serial(port=port, baudrate=baudrate, timeout=1)
        print(f"Connected to Arduino on {port}")
    except Exception as e:
        print(f"Failed to connect: {e}")

# read one temperature from arduino
def read_temperature():
    if connection and connection.in_waiting:
        try:
            line = connection.readline().decode('utf-8').strip()
            return line
        except:
            return None
    return None

# close connection
def close_arduino():
    global connection
    if connection and connection.is_open:
        connection.close()