import pandas as pd

def get_dashboard_data(chats: list) -> dict:
    """
    Processes a list of chat histories and returns a dictionary of dashboard stats.
    """
    if not chats:
        return {
            "total_projects": 0,
            "total_requirements": 0,
            "avg_requirements_per_project": 0,
            "priority_counts": pd.DataFrame({'Priority': ['Critical', 'High', 'Medium'], 'Count': [0, 0, 0]}),
            "recent_projects": []
        }

    total_projects = len(chats)
    total_requirements = 0
    priority_distribution = {'Critical': 0, 'High': 0, 'Medium': 0}

    for chat in chats:
        requirements = chat.get('requirements', [])
        total_requirements += len(requirements)
        
        scores = chat.get('prioritization_scores', {})
        if scores:
            for req in requirements:
                score = scores.get(req, 0)
                if score >= 8:
                    priority_distribution['Critical'] += 1
                elif score >= 5:
                    priority_distribution['High'] += 1
                else:
                    priority_distribution['Medium'] += 1

    avg_requirements = round(total_requirements / total_projects, 1) if total_projects > 0 else 0
    
    # Prepare data for charting
    priority_df = pd.DataFrame(list(priority_distribution.items()), columns=['Priority', 'Count'])

    # Get the 5 most recent projects for the table
    recent_projects = sorted(chats, key=lambda x: x.get('id', 0), reverse=True)[:5]
    
    return {
        "total_projects": total_projects,
        "total_requirements": total_requirements,
        "avg_requirements_per_project": avg_requirements,
        "priority_counts": priority_df,
        "recent_projects": recent_projects
    }