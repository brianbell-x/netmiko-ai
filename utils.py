import base64
from PIL import Image
import io
import os
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.box import ROUNDED
from datetime import datetime
from models import get_total_token_usage, TOKEN_COST

console = Console()

def encode_image_to_base64(image_path):
    try:
        with Image.open(image_path) as img:
            max_size = (1024, 1024)
            img.thumbnail(max_size, Image.DEFAULT_STRATEGY)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG')
            return base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
    except Exception as e:
        return f"Error encoding image: {str(e)}"

def parse_goals(response):
    import re
    goals = re.findall(r'Goal \d+: (.+)', response)
    return goals

def execute_goals(goals):
    # This function should be implemented based on your specific requirements
    # It might involve calling the chat_with_claude function for each goal
    pass

def save_chat(conversation_history):
    now = datetime.now()
    filename = f"Chat_{now.strftime('%Y%m%d_%H%M%S')}.md"
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write("# Netmiko AI Chat Log\n\n")
        for message in conversation_history:
            if message['role'] == 'user':
                f.write(f"## User\n\n{message['content']}\n\n")
            elif message['role'] == 'assistant':
                f.write(f"## Assistant\n\n{message['content']}\n\n")
    
    return filename

def read_file(path):
    try:
        with open(path, 'r') as f:
            content = f.read()
        return content
    except Exception as e:
        return f"Error reading file: {str(e)}"

def read_multiple_files(paths):
    results = {}
    for path in paths:
        try:
            with open(path, 'r') as f:
                content = f.read()
            results[path] = content
        except Exception as e:
            results[path] = f"Error reading file: {str(e)}"
    return results

def list_files(path="."):
    try:
        files = os.listdir(path)
        return "\n".join(files)
    except Exception as e:
        return f"Error listing files: {str(e)}"

def reset_conversation():
    return []

def display_token_usage():
    from rich.table import Table
    from rich.panel import Panel
    from rich.box import ROUNDED

    table = Table(box=ROUNDED)
    table.add_column("Model", style="cyan")
    table.add_column("Input", style="magenta")
    table.add_column("Output", style="magenta")
    table.add_column("Total", style="green")
    table.add_column("Cost ($)", style="red")

    token_usage = get_total_token_usage()
    total_cost = 0

    for model, tokens in token_usage.items():
        input_tokens = tokens['input']
        output_tokens = tokens['output']
        total_tokens = input_tokens + output_tokens

        input_cost = (input_tokens / 1_000_000) * TOKEN_COST[model]["input"]
        output_cost = (output_tokens / 1_000_000) * TOKEN_COST[model]["output"]
        model_cost = input_cost + output_cost
        total_cost += model_cost

        table.add_row(
            model.replace("MODEL", "").capitalize(),
            f"{input_tokens:,}",
            f"{output_tokens:,}",
            f"{total_tokens:,}",
            f"${model_cost:.4f}"
        )

    table.add_row(
        "Total",
        "",
        "",
        "",
        f"${total_cost:.4f}",
        style="bold"
    )

    console.print(table)