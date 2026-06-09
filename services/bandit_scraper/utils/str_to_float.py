import re

def str_to_float(val: str) -> float | int | None:
    """
    Converts a string representation of a number to float or int.
    
    Handles decimal commas, thousands separator dots, and internal whitespaces.
    
    Args:
        val (str): The numeric string to parse.
        
    Returns:
        float | int | None: The parsed numeric value, or None if conversion fails.
    """
    if val is None:
        return None
    
    try:
        val = re.sub(r'\s+', '', val)
        val = val.replace(',', '.')
        val = re.sub(r'(?<=\d)\.(?=\d{3}(?:\.|$))', '', val)
        value_float = float(val)
        if value_float.is_integer():
            return int(value_float)
        return value_float
    except ValueError:
        return None