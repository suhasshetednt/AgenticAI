# Next-Generation AI Agent Orchestration Dashboard
**Technical Architecture & UX Specification**

## Executive Summary
This document outlines the architecture, UX, and frontend engineering plan for a futuristic, enterprise-grade AI operations control center. Designed for multi-agent systems (e.g., LangGraph), it provides real-time observability, interactive debugging, and workflow orchestration. The aesthetic merges the polished darkness of Linear/Vercel with the deep observability of Datadog and LangSmith.

---

## 1. Frontend Architecture & Tech Stack

*   **Framework:** Next.js 14+ (App Router) for server components, fast routing, and API integrations.
*   **Library:** React 18 (with concurrent features).
*   **Styling:** Tailwind CSS (utility-first, highly customizable design system).
*   **Component Library:** shadcn/ui (radix-ui primitives, accessible, headless).
*   **Animation:** Framer Motion (fluid transitions, micro-interactions, layout animations).
*   **Graph Visualization:** React Flow (interactive node-based canvas, custom node types).
*   **State Management:** Zustand (global state, fast WebSocket updates) + React Query (server state, caching).
*   **Real-time:** WebSocket API + Server-Sent Events (SSE) for streaming LLM tokens.
*   **Persistence Backend:** FastAPI + PostgreSQL + Redis (assumed).

---

## 2. Directory Structure (Next.js)

```text
src/
├── app/
│   ├── (dashboard)/
│   │   ├── layout.tsx              # Main shell (Sidebar, Header, Bottom Panel)
│   │   ├── page.tsx                # Active Workflows Overview
│   │   └── run/[id]/page.tsx       # Live Execution Canvas (React Flow)
│   ├── api/                        # Next.js route handlers (auth, proxies)
│   └── globals.css                 # Tailwind base & design tokens
├── components/
│   ├── canvas/                     # React Flow custom nodes/edges
│   │   ├── AgentNode.tsx
│   │   ├── RouterNode.tsx
│   │   ├── AnimatedEdge.tsx
│   │   └── FlowControls.tsx
│   ├── panels/
│   │   ├── LiveActivityFeed.tsx    # Right sidebar terminal
│   │   ├── MetricsBottomBar.tsx    # Bottom observability charts
│   │   └── NodeDetailDrawer.tsx    # Right-slide drawer for node inspection
│   ├── shared/                     # Buttons, Badges, Loaders (shadcn/ui)
│   └── visual/                     # Glowing effects, gradient backgrounds
├── lib/
│   ├── store/                      # Zustand slices (flowStore, metricsStore)
│   ├── hooks/
│   │   ├── useWebSocket.ts         # Live streaming connection
│   │   └── useAgentGraph.ts        # Graph layout logic (Dagre/ELK)
│   └── utils.ts                    # tailwind-merge, clsx
└── types/
    ├── agent.ts                    # Agent, Task, Tool payload types
    └── flow.ts                     # Graph node/edge state types
```

---

## 3. UI/UX Design System

### 3.1 Color Palette (Tailwind Config)
```javascript
theme: {
  colors: {
    background: '#0A0A0A',      // Deep OLED black
    surface: '#111111',         // Slightly elevated panel
    surfaceHover: '#1A1A1A',
    border: '#222222',
    primary: '#3B82F6',         // Bright Blue (Active/Running)
    success: '#10B981',         // Emerald Green (Completed)
    warning: '#F59E0B',         // Amber (Pending/Waiting/HITL)
    error: '#EF4444',           // Rose Red (Failed)
    text: {
      main: '#EDEDED',
      muted: '#888888',
      code: '#4ADE80',
    }
  }
}
```

### 3.2 Typography & Spacing
*   **Font:** Inter (Primary UI) and JetBrains Mono (Logs/Code blocks).
*   **Spacing:** 4px baseline grid. UI elements use tight spacing (gap-2, p-4) to maximize information density without feeling cluttered.
*   **Glassmorphism:** `bg-surface/50 backdrop-blur-xl border border-white/5` for floating panels.

### 3.3 Framer Motion Animation Plan
*   **Edge Flow:** SVG `<path>` with `strokeDasharray` and `animate={{ strokeDashoffset: [0, -20] }}` to simulate data pulsing between agents.
*   **Node States:** 
    *   *Running:* `animate={{ boxShadow: "0 0 20px 0px rgba(59,130,246,0.5)" }}`
    *   *Failed:* Shake animation on trigger, pulsating red border.
*   **Layout Transitions:** `layoutId` for smooth expansion from a small log entry to the full Node Detail Drawer.
*   **Streaming Text:** Fade-in character by character using staggered children variants.

---

## 4. Dashboard Wireframe & Component Hierarchy

### 4.1 Main Layout Shell (`layout.tsx`)
A full-screen, non-scrolling interface.
*   **Top Bar (h-14):** Breadcrumbs (`Workflows / Data Pipeline / Run #1042`), global status indicator (Live/Paused), User Avatar.
*   **Center Canvas:** Takes up remaining space. React Flow interactive area.
*   **Right Sidebar (w-80):** Live Activity Feed (can be collapsed).
*   **Bottom Panel (h-48):** Global Observability Metrics (resizable, can be collapsed to a thin status bar).

### 4.2 The Canvas (React Flow)
**Custom Node Types:**
*   **`AgentNode`**: Displays Agent Name, current action (e.g., "Searching DB"), progress bar, token count, and a glowing border if `status === 'running'`.
*   **`ToolNode`**: Smaller sub-nodes attached to Agents, showing tool execution (e.g., `execute_sql`).

**Micro-interactions:**
*   Hovering over a node highlights incoming/outgoing edges and dims the rest of the graph.
*   Clicking a node slides open the `NodeDetailDrawer`.

### 4.3 Right Sidebar: Live Activity Feed
*   **Aesthetic:** Modern terminal. Darker background (`bg-[#050505]`).
*   **Components:**
    *   *LogItem:* Timestamp, severity color strip, Agent Name, Message.
    *   *Streaming Output:* LLM thoughts appear in real-time with a blinking cursor block `█`.
    *   *Filter Bar:* Toggles to show/hide "Thoughts", "Actions", "Errors", "Memory".

### 4.4 Bottom Panel: Observability Metrics
*   **Mini Dashboards:**
    *   *Token Burn Rate:* Live line chart updating every second (Recharts/Tremor).
    *   *Latency Distribution:* Bar chart showing execution time per agent.
    *   *Queue Health:* Number of pending tasks.

### 4.5 Node Detail Drawer (`NodeDetailDrawer.tsx`)
Slides in from the right over the Activity Feed. Contains shadcn/ui Tabs:
1.  **Prompt & Response:** Split pane. Left: System + User prompt. Right: Streaming Markdown response.
2.  **State/Memory:** JSON viewer (react-json-view) showing the full LangGraph state dictionary.
3.  **Trace:** Flame graph or timeline showing exact ms taken for API calls, tool execution, and generation.
4.  **Errors:** Red-tinted terminal showing stack traces with a "Replay Node" action button.

---

## 5. React Flow Graph Architecture

```typescript
// Custom Node Data Payload
interface AgentNodeData {
  id: string;
  label: string;
  role: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'human_approval';
  metrics: {
    tokens: number;
    latencyMs: number;
  };
  activeTool?: string;
}
```

*   **Layout Algorithm:** Use `dagrejs` or `elkjs` to auto-calculate node positions based on the directed acyclic graph (DAG) structure of LangGraph, updating layout dynamically as new nodes spawn (e.g., Tree of Thought branches).
*   **Animated Edges:** Use a custom `Edge` component that accepts a `status` prop. If the source node is running, render a glowing SVG particle moving along the path using Framer Motion.

---

## 6. WebSocket Event Architecture

The UI subscribes to a FastAPI WebSocket endpoint (`/ws/run/{run_id}`).

**Event Types Handled via Zustand:**
1.  `GRAPH_SPAWN`: Initializes the nodes and edges.
2.  `NODE_START`: Updates node status to 'running', triggers glow animation.
3.  `TOKEN_STREAM`: Appends raw string delta to the Node Detail Drawer and Activity Feed.
4.  `TOOL_CALL`: Adds a sub-node or log entry showing tool execution (e.g., `{"name": "git_commit", "args": {...}}`).
5.  `NODE_END`: Transitions node to 'completed' or 'failed', updates final token counts.
6.  `STATE_UPDATE`: Overwrites the memory JSON payload for the specific node.

*Store Implementation (Zustand):*
```javascript
const useFlowStore = create((set) => ({
  nodes: [],
  edges: [],
  logs: [],
  updateNodeStatus: (id, status) => set((state) => ({ ... })),
  addLogEntry: (log) => set((state) => ({ logs: [...state.logs, log] }))
}))
```

---

## 7. Advanced Visualization Features

### 7.1 Tree-of-Thought (ToT)
When an agent branches out, the graph spawns parallel nodes dynamically. 
*   **Visual:** Dead-end branches (pruned thoughts) fade to 30% opacity and turn gray. The "winning" path highlights with a thick success-green edge.

### 7.2 Human-in-the-Loop (HITL)
When LangGraph halts at an `interrupt_before` node:
*   **Visual:** The node pulses amber. A massive "Awaiting Approval" banner drops down.
*   **Interaction:** A glassmorphism modal presents the pending state and the proposed action, offering "Approve", "Reject", or "Modify Input" buttons.

### 7.3 Time-Travel Debugging (Replay)
*   **Scrubber Bar:** A timeline slider sits directly above the Bottom Panel.
*   **Action:** Dragging the slider resets the Zustand state to a specific timestamp, reversing edge animations and dimming nodes that haven't executed yet. 

---

## 8. AI Observability UX Best Practices

1.  **Don't Overwhelm:** LLMs produce massive amounts of tokens. The UI must truncate and collapse raw JSON and long thought chains by default. Use "Expand" interactions.
2.  **Color Means Meaning:** Reserve Red for hard crashes. Use Amber for LLM hallucinations/retries. Use Blue for active processing.
3.  **Context is King:** Always allow the user to click an error and immediately see the *exact prompt* and *state* that caused it.
4.  **Terminal Comfort:** Engineers love logs. The Activity Feed should support keyboard shortcuts (e.g., `/` to search, `Cmd+K` to clear).
5.  **Perception of Speed:** Use micro-animations on WebSockets to make the system feel blazingly fast, even if the LLM generation takes 10 seconds. Pulsing indicators assure the user the system isn't frozen.
