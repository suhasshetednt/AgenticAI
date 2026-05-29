# ADL Automated Delivery Pipeline Architecture

This diagram illustrates how the Multi-Agent system collaborates to automate the end-to-end delivery of data products for ASL Airlines.

```mermaid
graph TD
    %% Styling definitions
    classDef userNode fill:#2c3e50,stroke:#34495e,stroke-width:2px,color:#ecf0f1,rx:10px,ry:10px;
    classDef agentNode fill:#2980b9,stroke:#3498db,stroke-width:2px,color:#fff,rx:10px,ry:10px;
    classDef systemNode fill:#27ae60,stroke:#2ecc71,stroke-width:2px,color:#fff,rx:5px,ry:5px;
    classDef gitNode fill:#8e44ad,stroke:#9b59b6,stroke-width:2px,color:#fff,rx:10px,ry:10px;
    classDef docNode fill:#e67e22,stroke:#d35400,stroke-width:2px,color:#fff;

    %% Nodes
    User(("🧑‍💻 Data Engineer\n(CLI Menu)")):::userNode
    
    subgraph "Phase 1: Ingestion & Planning"
        JiraAgent["🛠️ Jira Agent\n(Extracts Reqs)"]:::agentNode
        Jira["Atlassian Jira\n(Backlog/Sprints)"]:::systemNode
    end
    
    subgraph "Phase 2: Specification"
        DocAgent["📝 Documentation Agent\n(Generates Specs)"]:::agentNode
        DocFile["Project Documentation\n(.docx format)"]:::docNode
    end
    
    subgraph "Phase 3: Data Engineering"
        DremioAgent["🐘 Dremio Agent\n(SQL Generation & VDS)"]:::agentNode
        Dremio["Dremio Cloud\n(Data Lakehouse)"]:::systemNode
        AutoFix{"Validation\nFailed?"}:::userNode
    end
    
    subgraph "Phase 4: Visualization"
        QlikAgent["📊 Qlik Agent\n(Dashboard Generation)"]:::agentNode
        Qlik["Qlik Sense Cloud\n(Workspaces)"]:::systemNode
    end
    
    subgraph "Phase 5: Version Control"
        GitAgent["🐙 GitHub Agent\n(Version Control)"]:::gitNode
        GitHub["GitHub Repo\n(origin/main)"]:::systemNode
    end

    %% Connections
    User -- "Selects Ticket" --> JiraAgent
    JiraAgent <-->|"API calls"| Jira
    JiraAgent -- "Parsed Requirements" --> DocAgent
    
    DocAgent -- "Generates" --> DocFile
    DocAgent -- "Passes Context" --> DremioAgent
    
    DremioAgent <-->|"API calls (Search/Create)"| Dremio
    DremioAgent -- "Validates SQL" --> AutoFix
    AutoFix -- "Yes (Auto-Heal)" --> DremioAgent
    AutoFix -- "No (Success)" --> QlikAgent
    
    QlikAgent <-->|"API calls"| Qlik
    QlikAgent -- "Completes Ticket" --> GitAgent
    
    GitAgent <-->|"git status / commit"| User
    GitAgent -- "Pushes changes" --> GitHub
```

### Key Workflow Characteristics:
1. **Human-in-the-Loop (HITL)**: You control the progression at major "gates" between agents.
2. **State Passing**: The `TicketRequirements` object acts as the central brain, carrying context (ticket ID, business logic, feedback) seamlessly from agent to agent.
3. **Auto-Healing**: The Dremio Agent captures live API errors and loops back onto itself to rewrite SQL dynamically.
4. **Autonomous Source Control**: The workflow seals itself by ensuring all agent-generated artifacts and code are versioned locally and remotely.
