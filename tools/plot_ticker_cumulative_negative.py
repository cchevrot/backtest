import matplotlib
matplotlib.use('Agg')  # Use Agg backend for non-interactive plotting
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import lz4.frame
import pickle
import os
import numpy as np
from price_logger import PriceLogger

def fmt(ts):
    """Format timestamp to string with hours adjusted."""
    return (datetime.fromtimestamp(ts) + timedelta(hours=-6)).strftime("%Y-%m-%d %H:%M:%S")

def resample_data(timestamps, prices, interval='5min'):
    """Resample price data to a specified time interval (e.g., 5 minutes)."""
    if not timestamps:
        return [], []
    
    # Convert timestamps to numpy datetime64 for easier manipulation
    times = np.array([np.datetime64(dt) for dt in timestamps])
    prices = np.array(prices)
    
    # Get start and end of the day
    start_date = timestamps[0].replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = start_date + timedelta(days=1)
    
    # Create time bins (e.g., every 5 minutes)
    bin_size = timedelta(minutes=5) if interval == '5min' else timedelta(minutes=int(interval))
    bins = [start_date]
    current = start_date
    while current < end_date:
        current += bin_size
        bins.append(current)
    
    # Aggregate prices within each bin (mean of prices)
    resampled_times = []
    resampled_prices = []
    for i in range(len(bins) - 1):
        start = bins[i]
        end = bins[i + 1]
        mask = (times >= np.datetime64(start)) & (times < np.datetime64(end))
        if mask.any():
            resampled_times.append(start + bin_size / 2)  # Use midpoint of bin
            resampled_prices.append(np.mean(prices[mask]))
    
    return resampled_times, resampled_prices

def calculate_cumulative_negative_differences(prices):
    """Calculate the cumulative sum of absolute negative price differences."""
    if len(prices) < 2:
        return np.array([])
    
    # Calculate price differences
    differences = np.diff(prices)
    
    # Take absolute value of negative differences, zero for positive
    negative_diffs = np.where(differences < 0, np.abs(differences), 0)
    
    # Calculate cumulative sum
    cumulative_negative = np.cumsum(negative_diffs)
    
    return cumulative_negative

def plot_ticker_cumulative_negative(ticker, data_file="data/06/20/prices_data.lz4", resample_interval='5min'):
    """Plot the price history and cumulative negative price differences for a given ticker over a day."""
    # Check if data file exists
    if not os.path.exists(data_file):
        print(f"Error: Data file {data_file} does not exist")
        return
    
    # Initialize PriceLogger
    logger = PriceLogger(data_file)
    
    # Lists to store data for plotting
    timestamps = []
    prices = []
    start_date = None
    
    # Read data for the specified ticker
    for timestamp, tck, price in logger.read_all():
        if tck == ticker:
            dt = datetime.fromtimestamp(timestamp) + timedelta(hours=-6)
            if start_date is None:
                start_date = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            # Only include data from the same day as the first timestamp
            if start_date <= dt < start_date + timedelta(days=1):
                timestamps.append(dt)
                prices.append(price)
    
    if not timestamps:
        print(f"No data found for ticker {ticker} in {data_file}")
        return
    
    # Resample data to reduce volatility
    resampled_times, resampled_prices = resample_data(timestamps, prices, resample_interval)
    
    if not resampled_times:
        print(f"No resampled data available for ticker {ticker}")
        return
    
    # Calculate cumulative sum of absolute negative differences
    cumulative_negative = calculate_cumulative_negative_differences(resampled_prices)
    cumulative_timestamps = resampled_times[1:] if len(cumulative_negative) > 0 else []  # Align with differences (skip first)
    
    # Create the figure with two subplots
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
    
    # Plot price history
    ax1.plot(resampled_times, resampled_prices, marker='o', linestyle='-', markersize=4)
    ax1.set_title(f"Price History for {ticker} on {start_date.strftime('%Y-%m-%d')} (5-min intervals)")
    ax1.set_ylabel("Price")
    ax1.grid(True)
    
    # Plot cumulative negative differences
    if len(cumulative_negative) > 0:
        ax2.plot(cumulative_timestamps, cumulative_negative, marker='o', linestyle='-', markersize=4, color='orange')
    ax2.set_ylabel("Cumulative Negative Diff")
    ax2.grid(True)
    
    # Format x-axis to show hours
    ax2.xaxis.set_major_formatter(plt.FuncFormatter(
        lambda x, _: mdates.num2date(x).strftime("%H:%M")
    ))
    ax2.xaxis.set_major_locator(mdates.HourLocator())  # One tick per hour
    
    # Rotate x-axis labels for better readability
    plt.xticks(rotation=45)
    
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    
    # Save the plot to a file
    output_file = f"{ticker}_price_cumulative_negative.png"
    plt.savefig(output_file)
    print(f"Plot saved as {output_file}")
    
    # Close the figure to free memory
    plt.close()

def main():
    """Run the plot function with a specified ticker."""
    ticker = "KWE"  # Replace with desired ticker symbol
    data_file = "data/06/18/prices_data.lz4"  # Default data file path
    plot_ticker_cumulative_negative(ticker, data_file)

if __name__ == "__main__":
    main()