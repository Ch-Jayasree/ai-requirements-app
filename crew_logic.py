import os
import json
from textwrap import dedent
from crewai import Agent, Task, Crew, Process
from langchain_community.chat_models import ChatLiteLLM

# --- API Key & LLM Setup ---
try:
    import streamlit as st
    if "GROQ_API_KEY" in st.secrets:
        os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
except ImportError:
    pass

if "GROQ_API_KEY" not in os.environ or not os.environ["GROQ_API_KEY"]:
    raise ValueError("GROQ_API_KEY is not set. Please add it to your environment variables or Streamlit secrets.")

llm = ChatLiteLLM(
    model="groq/llama-3.1-8b-instant",
    temperature=0.1,
)

# --- NEW: Business Rules Definition ---
# These are the strategic goals the validator will check against.
business_rules = {
    "product_vision": {
        "name": "FinTrack Pro",
        "tagline": "Effortless expense tracking for modern professionals.",
        "target_audience": "Tech-savvy individuals, freelancers, and small business owners."
    },
    "monetization_model": {
        "model": "Freemium Subscription",
        "free_tier_limits": "Up to 50 manual transactions per month, standard reporting.",
        "premium_features": ["Unlimited transactions", "Automatic bank account sync", "Advanced analytics", "Receipt scanning", "Data export"]
    },
    "technical_constraints": {
        "platforms": "Web application first, mobile apps are out of scope for V1.",
        "integrations": "Third-party integrations require significant review and are generally post-V1."
    }
}


# --- AGENTS ---

strategic_analyst = Agent(
    role="Strategic Product Lead",
    goal="Quickly identify the 3-4 most critical, high-level questions needed to understand a new project idea.",
    backstory=dedent("""
        You are a seasoned product executive who thinks in terms of strategy, not minor features.
        Your talent is cutting through the noise to find the key questions that define a project's soul.
        """),
    llm=llm,
    verbose=False,
    allow_delegation=False
)

refinement_specialist = Agent(
    role="Requirements Refinement Specialist",
    goal="Update a list of requirements based on a user's answer to a specific question.",
    backstory=dedent("""
        You are a meticulous analyst. You are given a list of requirements, one question, and one answer.
        Your only job is to logically integrate the answer into the requirements list.
        """),
    llm=llm,
    verbose=False,
    allow_delegation=False
)

# NEW: Re-introducing the Business Validator Agent
business_validator = Agent(
    role="Business Logic & Strategy Expert",
    goal=f"Validate a list of proposed software requirements against a strict set of business rules. Identify any conflicts, premium feature suggestions, or out-of-scope items.",
    backstory=dedent(f"""
        You are the guardian of the product strategy. You have a deep understanding of the business goals, encoded in the rules below. 
        Your job is to meticulously review every proposed requirement and flag anything that doesn't align, suggesting how it could be changed or noting it as a premium feature.
        Your output is a clear, validated list of requirements with annotations.

        *Business Rules:*
        {json.dumps(business_rules, indent=2)}
        """),
    llm=llm,
    verbose=False
)


prioritizer_agent = Agent(
    role="Product Manager",
    goal="Analyze prioritization scores and provide a balanced, prioritized list with rationale.",
    backstory="You are a master of prioritization, deciding what gets built first.",
    llm=llm,
    verbose=False
)

summarizer_agent = Agent(
    role="Lead Technical Writer",
    goal="Create a professional and structured Software Requirements Specification (SRS) document from a list of prioritized requirements.",
    backstory="You are a highly skilled technical writer who crafts comprehensive, clear, and professional documentation.",
    llm=llm,
    verbose=False
)

# --- CREW LOGIC FUNCTIONS ---

def analyze_initial_request(initial_request: str) -> str:
    # This function is unchanged.
    analysis_task = Task(
        description=f"""
            Analyze the following user request. Extract a preliminary list of requirements and generate a list of the 3-4 most critical, high-level questions.
            User Request: --- {initial_request} ---
            You MUST respond with a single, valid JSON object with keys 'initial_requirements' and 'clarifying_questions'.
        """,
        agent=strategic_analyst,
        expected_output="A single valid JSON object."
    )
    crew = Crew(agents=[strategic_analyst], tasks=[analysis_task], process=Process.sequential)
    return str(crew.kickoff())

def refine_requirements_with_answer(current_requirements: list, question: str, answer: str) -> str:
    # This function is unchanged.
    refinement_task = Task(
        description=f"""
            A user was asked: "{question}". They answered: "{answer}".
            Update the current requirements list based on their answer: {json.dumps(current_requirements)}.
            You MUST respond with a single, valid JSON object with a single key: 'updated_requirements'.
        """,
        agent=refinement_specialist,
        expected_output="A single valid JSON object."
    )
    crew = Crew(agents=[refinement_specialist], tasks=[refinement_task], process=Process.sequential)
    return str(crew.kickoff())

# UPDATED: This function now includes the validation step.
def finalize_requirements_document(final_requirements: list, prioritization_scores: dict) -> str:
    # NEW: A validation task that runs before prioritization.
    validate_task = Task(
        description=f"""
            Review the following list of software requirements. Cross-reference each item against the business rules provided in your goal.
            Your output should be a revised list of requirements, with annotations added in parentheses for any item that is a premium feature, out of scope, or needs modification.

            Requirements to Validate:
            {json.dumps(final_requirements, indent=2)}
        """,
        agent=business_validator,
        expected_output="A revised list of requirements with validation annotations."
    )

    prioritize_task = Task(
        description=f"""
            Analyze the user's prioritization scores for the validated requirements and create a final, ranked list.
            Provide a brief justification for each priority level (Critical, High, Medium).

            Scores: {json.dumps(prioritization_scores, indent=2)}
        """,
        agent=prioritizer_agent,
        context=[validate_task], # This task now depends on the output of the validation task.
        expected_output="A prioritized list of requirements with justifications."
    )

    summarize_task = Task(
        description=f"""
            Generate a professional Software Requirements Specification (SRS) document in Markdown format based on the prioritized list of requirements.
            
            # UPDATED: The template now includes a Validation Summary section.
            You MUST follow this template exactly:

            # Software Requirements Specification

            ## 1. Introduction
            (Write a brief, 1-2 paragraph executive summary of the project based on the requirements.)

            ## 2. Validation Summary
            (Based on the context from the validation task, briefly summarize how the requirements align with the business rules. Note any features that were flagged as Premium or out of scope.)

            ## 3. Functional Requirements
            (List the functional requirements here, grouped by their priority.)

            ### 3.1. Critical Priority
            - (List critical priority requirements here)

            ### 3.2. High Priority
            - (List high priority requirements here)

            ### 3.3. Medium Priority
            - (List medium priority requirements here)
            
            ## 4. Conclusion & Next Steps
            (Write a brief concluding paragraph.)
        """,
        agent=summarizer_agent,
        context=[prioritize_task],
        expected_output="A complete and professionally formatted SRS markdown document."
    )

    # UPDATED: The crew now includes the business_validator agent.
    project_crew = Crew(
        agents=[business_validator, prioritizer_agent, summarizer_agent],
        tasks=[validate_task, prioritize_task, summarize_task],
        process=Process.sequential
    )
    return str(project_crew.kickoff())