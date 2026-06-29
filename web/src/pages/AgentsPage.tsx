import { useEffect, useState, useRef } from "react";
import { Bot, Plus, Trash2, Send, X, Loader2, Terminal } from "lucide-react";
import { api } from "@/lib/api";
import type { AgentInfo } from "@/lib/api";
import { useToast } from "@/hooks/useToast";
import { Toast } from "@/components/Toast";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function fmtUptime(seconds?: number): string {
  if (!seconds && seconds !== 0) return "";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m ${seconds % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export default function AgentsPage() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showSpawn, setShowSpawn] = useState(false);
  const [spawnPrompt, setSpawnPrompt] = useState("");
  const [spawnMode, setSpawnMode] = useState("interactive");
  const [spawning, setSpawning] = useState(false);
  const [viewAgent, setViewAgent] = useState<string | null>(null);
  const [agentOutput, setAgentOutput] = useState("");
  const [agentMsg, setAgentMsg] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const { toast, showToast } = useToast();

  const loadAgents = () => {
    api.getAgents().then((r) => setAgents(r.agents)).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => {
    loadAgents();
    const iv = setInterval(loadAgents, 10000);
    return () => clearInterval(iv);
  }, []);

  // Poll agent output when viewing
  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (!viewAgent) { setAgentOutput(""); return; }

    const poll = () => {
      api.getAgent(viewAgent).then((a) => {
        setAgentOutput(a.output || "");
        if (a.status === "dead" || a.status === "done") {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      }).catch(() => {});
    };
    poll();
    pollRef.current = setInterval(poll, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [viewAgent]);

  const handleSpawn = async () => {
    if (!spawnPrompt.trim()) return;
    setSpawning(true);
    try {
      await api.spawnAgent({ prompt: spawnPrompt.trim(), mode: spawnMode });
      showToast("Agent spawned", "success");
      setSpawnPrompt("");
      setShowSpawn(false);
      loadAgents();
    } catch (e: any) {
      showToast(`Spawn failed: ${e.message}`, "error");
    } finally {
      setSpawning(false);
    }
  };

  const handleKill = async (name: string) => {
    try {
      await api.killAgent(name);
      showToast(`Killed ${name}`, "success");
      if (viewAgent === name) setViewAgent(null);
      loadAgents();
    } catch (e: any) {
      showToast(`Kill failed: ${e.message}`, "error");
    }
  };

  const handleSendMsg = async () => {
    if (!agentMsg.trim() || !viewAgent) return;
    try {
      await api.sendAgentMessage(viewAgent, agentMsg.trim());
      setAgentMsg("");
    } catch (e: any) {
      showToast(`Send failed: ${e.message}`, "error");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Toast toast={toast} />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-muted-foreground" />
          <h1 className="text-base font-semibold">Agents</h1>
          <Badge variant="secondary" className="text-xs">{agents.length}</Badge>
        </div>
        <Button size="sm" className="text-xs h-8" onClick={() => setShowSpawn(true)}>
          <Plus className="h-3 w-3 mr-1" /> Spawn
        </Button>
      </div>

      {/* Spawn modal */}
      {showSpawn && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2"><Plus className="h-4 w-4" /> Spawn Agent</CardTitle>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setShowSpawn(false)}><X className="h-3 w-3" /></Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <textarea
              className="flex min-h-[60px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              placeholder="Task prompt for the agent..."
              value={spawnPrompt}
              onChange={(e) => setSpawnPrompt(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <select className="rounded-md border border-input bg-transparent px-2 py-1 text-sm" value={spawnMode} onChange={(e) => setSpawnMode(e.target.value)}>
                <option value="interactive">Interactive</option>
                <option value="oneshot">One-shot</option>
              </select>
              <Button onClick={handleSpawn} disabled={spawning || !spawnPrompt.trim()} className="ml-auto">
                {spawning ? "Spawning..." : "Spawn"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Agent output viewer */}
      {viewAgent && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Terminal className="h-4 w-4" /> {viewAgent}
              </CardTitle>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setViewAgent(null)}><X className="h-3 w-3" /></Button>
            </div>
          </CardHeader>
          <CardContent>
            <pre className="bg-background border border-border rounded-md p-3 text-xs font-mono leading-4 overflow-auto max-h-[300px] whitespace-pre-wrap">
              {agentOutput || "Waiting for output..."}
            </pre>
            <div className="flex items-center gap-2 mt-2">
              <Input
                placeholder="Send message to agent..."
                value={agentMsg}
                onChange={(e) => setAgentMsg(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleSendMsg(); }}
                className="text-xs h-8"
              />
              <Button size="icon" className="h-8 w-8 shrink-0" onClick={handleSendMsg}>
                <Send className="h-3 w-3" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Agent list */}
      {agents.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Bot className="h-8 w-8 mb-3 opacity-40" />
          <p className="text-sm font-medium">No agents running</p>
          <p className="text-xs mt-1 opacity-60">Tap Spawn to start one</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {agents.map((a) => (
            <div key={a.name} className="flex items-center justify-between border border-border p-3 rounded-md hover:bg-secondary/30 transition-colors">
              <div className="flex flex-col gap-0.5 cursor-pointer min-w-0" onClick={() => setViewAgent(a.name)}>
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${a.status === "running" ? "bg-success animate-pulse" : "bg-muted-foreground"}`} />
                  <span className="text-sm font-medium truncate">{a.display_name || a.name}</span>
                  <Badge variant="outline" className="text-[10px]">{a.mode}</Badge>
                  {a.worktree && <Badge variant="outline" className="text-[10px]">worktree</Badge>}
                </div>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground truncate">
                  <span className="truncate">{a.model}</span>
                  <span className="text-border">·</span>
                  <span>{fmtUptime(a.uptime)}</span>
                </div>
              </div>
              <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-destructive shrink-0" onClick={() => handleKill(a.name)}>
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
