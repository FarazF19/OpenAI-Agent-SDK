from agents import Agent, Runner
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

agent = Agent(
    name="Assistant", 
    instructions="You are a helpful assistant",
    model="gpt-4o-mini"
)

def main():
    result = Runner.run_sync(agent, "Write a haiku about recursion in programming.")
    print(result.final_output)

if __name__ == "__main__":
    main()