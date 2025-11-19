import numpy as np

# removes noisy readings / outliers, returns filtered list of readings
def detect_outliers(temperatures, threshold=3.0):
    if len(temperatures) < 3:
        return temperatures, 0
    filtered = []
    outlier_count = 0
    for i in range(len(temperatures)):
        window = temperatures[max(0, i-5):min(len(temperatures), i+5)]
        avg = np.mean(window)
        if abs(temperatures[i] - avg) > threshold:
            outlier_count += 1
        else:
            filtered.append(temperatures[i])
    return filtered, outlier_count

# calculates second derivative of temp changes over time, higher values indicate more drastic temp changes
def calculate_variability(temperatures):
    if len(temperatures) < 3:
        return 0.0
    second_derivs = []
    for i in range(1, len(temperatures) - 1):
        deriv = temperatures[i+1] - 2*temperatures[i] + temperatures[i-1]
        second_derivs.append(abs(deriv))
    return np.mean(second_derivs) if second_derivs else 0.0