from anthropic import Anthropic
import os

# Model constants
MAINMODEL = "claude-3-5-sonnet-20240620"
TOOLCHECKERMODEL = "claude-3-5-sonnet-20240620"
CODEEDITORMODEL = "claude-3-5-sonnet-20240620"
CODEEXECUTIONMODEL = "claude-3-5-sonnet-20240620"

# Initialize Anthropic client
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Token tracking variables
main_model_tokens = {'input': 0, 'output': 0}
tool_checker_tokens = {'input': 0, 'output': 0}
code_editor_tokens = {'input': 0, 'output': 0}
code_execution_tokens = {'input': 0, 'output': 0}

# Token cost dictionary
TOKEN_COST = {
    "MAINMODEL": {"input": 3.00, "output": 15.00},
    "TOOLCHECKERMODEL": {"input": 3.00, "output": 15.00},
    "CODEEDITORMODEL": {"input": 3.00, "output": 15.00},
    "CODEEXECUTIONMODEL": {"input": 3.00, "output": 15.00}
}

def update_token_usage(model_type, input_tokens, output_tokens):
    """
    Update the token usage for a specific model type.
    """
    global main_model_tokens, tool_checker_tokens, code_editor_tokens, code_execution_tokens
    if model_type == "main":
        main_model_tokens['input'] += input_tokens
        main_model_tokens['output'] += output_tokens
    elif model_type == "tool_checker":
        tool_checker_tokens['input'] += input_tokens
        tool_checker_tokens['output'] += output_tokens
    elif model_type == "code_editor":
        code_editor_tokens['input'] += input_tokens
        code_editor_tokens['output'] += output_tokens
    elif model_type == "code_execution":
        code_execution_tokens['input'] += input_tokens
        code_execution_tokens['output'] += output_tokens

def get_total_token_usage():
    """
    Get the total token usage across all models.
    """
    return {
        "MAINMODEL": main_model_tokens,
        "TOOLCHECKERMODEL": tool_checker_tokens,
        "CODEEDITORMODEL": code_editor_tokens,
        "CODEEXECUTIONMODEL": code_execution_tokens
    }