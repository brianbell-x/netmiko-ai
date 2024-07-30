import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Check if API keys are present
if not ANTHROPIC_API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
if not TAVILY_API_KEY:
    raise ValueError("TAVILY_API_KEY not found in environment variables")

# Constants
MAX_CONTEXT_TOKENS = 200000
CONTINUATION_EXIT_PHRASE = "AUTOMODE_COMPLETE"
MAX_CONTINUATION_ITERATIONS = 25

# Load prompts from files
def load_prompt(filename):
    with open(os.path.join('prompts', filename), 'r') as file:
        return file.read()

BASE_SYSTEM_PROMPT = load_prompt('base_system_prompt.txt')
AUTOMODE_SYSTEM_PROMPT = load_prompt('automode_system_prompt.txt')

def update_system_prompt(current_iteration=None, max_iterations=None):
    chain_of_thought_prompt = load_prompt('chain_of_thought_prompt.txt')
    
    if current_iteration is not None and max_iterations is not None:
        iteration_info = f"You are currently on iteration {current_iteration} out of {max_iterations} in automode."
        return BASE_SYSTEM_PROMPT + "\n\n" + AUTOMODE_SYSTEM_PROMPT.format(iteration_info=iteration_info) + "\n\n" + chain_of_thought_prompt
    else:
        return BASE_SYSTEM_PROMPT + "\n\n" + chain_of_thought_prompt

# Conda environment settings
CONDA_ENV_NAME = "netmikoai"
PYTHON_VERSION = "3.11"