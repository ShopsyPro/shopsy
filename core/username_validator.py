"""
Username validation utilities
"""

import os

def is_reserved_username(username):
    """
    Check if a username is in the reserved list
    
    Args:
        username (str): The username to check
        
    Returns:
        bool: True if username is reserved, False otherwise
    """
    if not username:
        return False
    
    # Convert to lowercase for case-insensitive comparison
    username = username.lower().strip()
    
    # Get the path to the reserved usernames file
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reserved_file = os.path.join(current_dir, 'reserved_usernames.txt')
    
    try:
        with open(reserved_file, 'r') as f:
            reserved_usernames = [line.strip().lower() for line in f if line.strip()]
            return username in reserved_usernames
    except FileNotFoundError:
        # If the file doesn't exist, return False (allow all usernames)
        return False
    except Exception:
        # If there's any other error reading the file, return False
        return False

def get_reserved_username_message():
    """
    Get the message to display when a reserved username is used
    
    Returns:
        str: The error message
    """
    return "This is a reserved username. Please contact support or choose another username." 