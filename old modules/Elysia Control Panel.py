// Elysia Control Panel — React UI with Mutation Button
import React, { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";

function MutationList() {
  const [mutations, setMutations] = React.useState([]);
  const [message, setMessage] = React.useState("");

  React.useEffect(() => {
    fetch("http://127.0.0.1:8000/mutation-queue")
      .then(res => res.json())
      .then(setMutations)
      .catch(() => setMutations([]));
  }, []);

  const handleDecision = async (idx, decision) => {
    const m = mutations[idx];
    const endpoint = `http://127.0.0.1:8000/mutation-decision`;
    try {
      await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...m, decision })
      });
      setMutations(mutations.filter((_, i) => i !== idx));
      setMessage(`Mutation ${decision}ed.`);
    } catch {
      setMessage("Failed to process decision.");
    }
  };

  if (mutations.length === 0) return <div className="text-xs text-gray-500">No mutations in queue.</div>;
  return (
    <div>
      {message && <div className="text-xs text-green-600 pb-2">{message}</div>}
      <ul className="text-xs space-y-2">
        {mutations.map((m, idx) => (
          <li key={idx} className="border-b pb-1">
            <div><span className="font-semibold">{m.module}</span> from <span className="text-blue-600">{m.origin_node}</span></div>
            <div className="text-gray-600">{m.proposed_change}</div>
            <div className="text-gray-400">Trust: {m.trust_score} | Utility: {m.utility_rating} | Passed: {m.test_passed ? "Yes" : "No"}</div>
            <div className="pt-1 space-x-2">
              <button className="text-green-700 hover:underline" onClick={() => handleDecision(idx, "accept")}>Accept</button>
              <button className="text-red-700 hover:underline" onClick={() => handleDecision(idx, "reject")}>Reject</button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function MonetizationSummary() {
  const [data, setData] = React.useState({});

  React.useEffect(() => {
    Promise.all([
      fetch("http://127.0.0.1:8000/stripe-balance").then(r => r.json()),
      fetch("http://127.0.0.1:8000/gumroad-income").then(r => r.json())
    ]).then(([stripe, gumroad]) => setData({ stripe, gumroad }));
  }, []);

  return (
    <div className="text-xs space-y-1">
      <div className="font-medium text-sm">Stripe</div>
      {data.stripe?.status === "ok" ? (
        <div>Available Balance: ${data.stripe.balance.available[0].amount / 100} {data.stripe.balance.available[0].currency.toUpperCase()}</div>
      ) : (
        <div className="text-red-600">{data.stripe?.message || "No Stripe key provided."}</div>
      )}

      <div className="font-medium pt-2 text-sm">Gumroad</div>
      {data.gumroad?.status === "ok" ? (
        <div>Sales: {data.gumroad.sales_count} — Total Income: ${data.gumroad.total_income}</div>
      ) : (
        <div className="text-red-600">{data.gumroad?.message || "No Gumroad credentials provided."}</div>
      )}
    </div>
  );
}

function EarningsLog() {
  const [log, setLog] = React.useState([]);

  React.useEffect(() => {
    fetch("http://127.0.0.1:8000/income-log")
      .then(res => res.json())
      .then(setLog)
      .catch(() => setLog([]));
  }, []);

  if (log.length === 0) return <div className="text-xs text-gray-500">No earnings logged yet.</div>;
  return (
    <ul className="text-xs space-y-2">
      {log.map((entry, idx) => (
        <li key={idx} className="border-b pb-1">
          <div><span className="font-semibold">{entry.subnode}</span> earned ${entry.amount} via {entry.method} ({entry.context})</div>
          <div className="text-gray-500">{entry.timestamp}</div>
        </li>
      ))}
    </ul>
  );
}

function ProjectLedger() {
  const [ledger, setLedger] = React.useState([]);

  React.useEffect(() => {
    fetch("http://127.0.0.1:8000/project-ledger")
      .then(res => res.json())
      .then(setLedger)
      .catch(() => setLedger([]));
  }, []);

  if (ledger.length === 0) return <div className="text-xs text-gray-500">No project contributions logged.</div>;
  return (
    <ul className="text-xs space-y-2">
      {ledger.map((entry, idx) => (
        <li key={idx} className="border-b pb-1">
          <div><span className="font-semibold">{entry.project}</span> — {entry.subnode} contributed {entry.amount} via {entry.contribution_type}</div>
          <div className="text-gray-500">{entry.timestamp}</div>
        </li>
      ))}
    </ul>
  );
}

function ProjectIncome() {
  const [income, setIncome] = React.useState([]);

  React.useEffect(() => {
    fetch("http://127.0.0.1:8000/project-income")
      .then(res => res.json())
      .then(setIncome)
      .catch(() => setIncome([]));
  }, []);

  if (income.length === 0) return <div className="text-xs text-gray-500">No project income logged.</div>;
  return (
    <ul className="text-xs space-y-2">
      {income.map((entry, idx) => (
        <li key={idx} className="border-b pb-1">
          <div><span className="font-semibold">{entry.project}</span> earned ${entry.amount} via {entry.method}</div>
          <div className="text-gray-500">{entry.timestamp}</div>
        </li>
      ))}
    </ul>
  );
}

function TrustNetwork() {
  const [nodes, setNodes] = React.useState([]);

  React.useEffect(() => {
    fetch("http://127.0.0.1:8000/trust-registry")
      .then(res => res.json())
      .then(setNodes)
      .catch(() => setNodes([]));
  }, []);

  if (nodes.length === 0) return <div className="text-xs text-gray-500">No trust data available.</div>;
  return (
    <ul className="text-xs space-y-2">
      {nodes.filter(n => n.visibility?.share_trust_score !== false).map((entry, idx) => (
        <li key={idx} className="border-b pb-1">
          <div><span className=\"font-semibold\">{entry.anonymous_mode ? "anon_node" : entry.node}</span>: Trust Score {entry.trust_score}</div>
          {entry.module_scores && Object.entries(entry.module_scores).map(([mod, score], i) => (
            <div key={i} className=\"pl-2 text-gray-500\">{mod}: {score.toFixed(2)}</div>
          ))}
          <div className="text-gray-500">{entry.history.slice(-1)[0]?.reason || "No recent update."}</div>
        </li>
      ))}
    </ul>
  );
}

function MutationReview() {
  const [mutations, setMutations] = React.useState([]);

  React.useEffect(() => {
    fetch("http://127.0.0.1:8000/mutation-review")
      .then(res => res.json())
      .then(setMutations)
      .catch(() => setMutations([]));
  }, []);

  const updateMutation = (index, action) => {
    const updated = [...mutations];
    updated[index].status = action;
    setMutations(updated);
  };

  if (mutations.length === 0) return <div className="text-xs text-gray-500">No pending mutations.</div>;
  return (
    <ul className="text-xs space-y-2">
      {mutations.filter(m => m.status === "pending").map((entry, idx) => (
        <li key={idx} className="border-b pb-1">
          <div><strong>{entry.module}</strong> by <em>{entry.subnode}</em> (Trust {entry.mutation_trust_score})</div>
          <div className="text-gray-600">{entry.summary}</div>
          <div className="space-x-2 pt-1">
            <button className="text-green-600 text-xs" onClick={() => updateMutation(idx, "approved")}>Approve</button>
            <button className="text-red-600 text-xs" onClick={() => updateMutation(idx, "rejected")}>Reject</button>
          </div>
        </li>
      ))}
    </ul>
  );
}

function TaskRoutingLog() {
  const [log, setLog] = React.useState([]);

  React.useEffect(() => {
    fetch("http://127.0.0.1:8000/task-log")
      .then(res => res.json())
      .then(setLog)
      .catch(() => setLog([]));
  }, []);

  if (log.length === 0) return <div className="text-xs text-gray-500">No task assignments yet.</div>;
  return (
    <ul className="text-xs space-y-2">
      {log.map((entry, idx) => (
        <li key={idx} className="border-b pb-1">
          <div><strong>{entry.task_type}</strong> → <em>{entry.assigned_to}</em> (Trust {entry.trust_score})</div>
          <div className="text-gray-500">{entry.timestamp}</div>
        </li>
      ))}
    </ul>
  );
}

function CoreCreditRedemption() {
  const [balance, setBalance] = React.useState(0);
  const [catalog, setCatalog] = React.useState([]);
  const [message, setMessage] = React.useState(null);

  React.useEffect(() => {
    fetch("http://127.0.0.1:8000/credit-catalog").then(res => res.json()).then(setCatalog);
    fetch("http://127.0.0.1:8000/credit-balance?subnode=nodeB").then(res => res.json()).then(data => setBalance(data.balance));
  }, []);

  const redeem = async (item) => {
    const res = await fetch("http://127.0.0.1:8000/spend-credits", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subnode: "nodeB", purpose: item.key, cost: item.cost })
    });
    const data = await res.json();
    setMessage(data.status === "approved" ? `Success: ${item.label}` : `Error: ${data.reason}`);
    if (data.new_balance !== undefined) setBalance(data.new_balance);
  };

  return (
    <div className="space-y-2">
      <div className="text-xs">Current Balance: <strong>{balance}</strong> CoreCredits</div>
      {catalog.map((item, idx) => (
        <div key={idx} className="border-b pb-2">
          <div className="text-sm">{item.label} ({item.cost} credits)</div>
          <button className="text-xs text-blue-600" onClick={() => redeem(item)}>Redeem</button>
        </div>
      ))}
      {message && <div className="text-xs pt-2 text-green-700">{message}</div>}
    </div>
  );
}

function ReputationTagList() {
  const [tags, setTags] = React.useState({});

  React.useEffect(() => {
    fetch("http://127.0.0.1:8000/reputation-tags")
      .then(res => res.json())
      .then(setTags);
  }, []);

  return (
    <ul className="text-xs space-y-2">
      {Object.entries(tags).map(([node, tagList]) => (
        <li key={node} className="border-b pb-1">
          <strong>{node}</strong>: {tagList.join(", ")}
        </li>
      ))}
    </ul>
  );
}

export default function ElysiaControlPanel() {
  const [activity, setActivity] = useState([]);
  const [error, setError] = useState(null);
  const [statusMsg, setStatusMsg] = useState("");

  const fetchActivity = () => {
    fetch("http://127.0.0.1:8000/activity-log")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load activity log");
        return res.json();
      })
      .then(setActivity)
      .catch((err) => setError(err.message));
  };

  useEffect(() => {
    fetchActivity();
  }, []);

  const handleTrigger = async (type) => {
    const endpoint = `http://127.0.0.1:8000/trigger/${type}`;
    try {
      const res = await fetch(endpoint, { method: "POST" });
      const data = await res.json();
      setStatusMsg(data.message);
      fetchActivity();
    } catch (e) {
      setStatusMsg("Failed to trigger " + type);
    }
  };

  const totalTokensSpent = activity.reduce((acc, entry) => acc + Math.max(0, entry.tokens), 0);
  const totalHarvested = activity.reduce((acc, entry) => acc + (entry.tokens < 0 ? Math.abs(entry.tokens) : 0), 0);
  const netTokenFlow = totalHarvested - totalTokensSpent;

  return (
    <div className="p-6 space-y-4 bg-gray-50 min-h-screen">
      <h1 className="text-3xl font-bold tracking-tight">Elysia Control Panel</h1>

      <Card>
        <CardContent className="py-4">
          <div className="text-sm text-muted-foreground">System Status: <span className="text-green-600 font-medium">Online</span></div>
          <div className="mt-1 text-xs">Model: GPT-4 | Token Budget: 42 | Income Forecast: $124.50</div>
        </CardContent>
      </Card>

      <Tabs defaultValue="goals" className="w-full">
        <TabsList className="grid grid-cols-7 w-full">
          <TabsTrigger value="goals">Goals</TabsTrigger>
          <TabsTrigger value="echo">Echo Log</TabsTrigger>
          <TabsTrigger value="tokens">Tokens</TabsTrigger>
          <TabsTrigger value="monetization">Monetization</TabsTrigger>
          <TabsTrigger value="controls">Controls</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
          <TabsTrigger value="mutations">Mutations</TabsTrigger>
        </TabsList>
          <TabsTrigger value="reputation">Reputation</TabsTrigger>
          <TabsTrigger value="credits">CoreCredits</TabsTrigger>
          <TabsTrigger value="assignments">Task Routing</TabsTrigger>
          <TabsTrigger value="mutations">Mutation Review</TabsTrigger>
          <TabsTrigger value="trust">Trust Network</TabsTrigger>
          <TabsTrigger value="project-income">Project Income</TabsTrigger>
          <TabsTrigger value="projects">Project Ledger</TabsTrigger>
          <TabsTrigger value="earnings">Earnings Log</TabsTrigger>
          <TabsTrigger value="ai">Connect AI Services</TabsTrigger>
          <TabsTrigger value="payments">Connect Payments</TabsTrigger>

        <TabsContent value="goals">
          <Card><CardContent className="p-4">Active goals will appear here.</CardContent></Card>
        </TabsContent>

        <TabsContent value="echo">
          <Card><CardContent className="p-4 text-sm">Recent EchoThread entries...</CardContent></Card>
        </TabsContent>

        <TabsContent value="tokens">
          <Card>
            <CardContent className="p-4 text-sm space-y-2">
              <div className="font-medium">Token Economy</div>
              <ul className="text-xs list-disc list-inside">
                <li>Total Tokens Spent: {totalTokensSpent}</li>
                <li>Tokens Harvested from Subnodes: {totalHarvested}</li>
                <li>Net Flow: {netTokenFlow > 0 ? "+" : ""}{netTokenFlow} tokens</li>
              </ul>
              <div className="text-muted-foreground text-xs mt-2">This reflects system self-sufficiency and distributed efficiency.</div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="monetization">
          <Card>
            <CardContent className="p-4 text-sm space-y-2">
              <div className="font-medium">Live Monetization Summary</div>
              <MonetizationSummary />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="controls">
          <Card><CardContent className="p-4 space-y-3">
            <Button onClick={() => handleTrigger("runtime")}>Run RuntimeLoop</Button>
            <Button variant="outline" onClick={() => handleTrigger("monetization")}>Trigger Monetization</Button>
            <Button variant="secondary" onClick={() => handleTrigger("mutation")}>Run Mutation Cycle</Button>
            {statusMsg && <div className="text-xs text-muted-foreground">{statusMsg}</div>}
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="activity">
          <Card>
            <CardContent className="p-4 text-sm space-y-2">
              <div className="font-medium mb-2">Recent Activity:</div>
              {error ? (
                <div className="text-red-500 text-xs">{error}</div>
              ) : (
                <ul className="space-y-1 text-xs">
                  {activity.map((item, idx) => (
                    <li key={idx} className="border-b pb-1">
                      <span className="font-semibold">[{item.timestamp}]</span> {item.source} → {item.module} → {item.task_type}<br />
                      Used <span className="font-semibold">{item.model}</span> ({item.tokens} tokens): {item.result}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      <TabsContent value="mutations">
          <Card>
            <CardContent className="p-4 text-sm space-y-2">
              <div className="font-medium mb-2">Queued Mutations:</div>
              <div className="text-xs text-muted-foreground">Live preview of proposed subnode mutations sent to Core.</div>
              <MutationList />
            </CardContent>
          </Card>
        </TabsContent>

      <TabsContent value="payments">
          <Card>
            <CardContent className="p-4 space-y-4 text-sm">
              <div className="font-medium">Stripe Credentials</div>
              <input id="stripeKey" className="w-full p-2 border rounded text-xs" placeholder="Stripe Secret Key" />
              <input id="stripeID" className="w-full p-2 border rounded text-xs" placeholder="Stripe Account ID" />

              <div className="font-medium pt-4">Gumroad Credentials</div>
              <input id="gumroadToken" className="w-full p-2 border rounded text-xs" placeholder="Gumroad Access Token" />
              <input id="gumroadUser" className="w-full p-2 border rounded text-xs" placeholder="Gumroad User ID" />

              <button className="text-xs bg-blue-600 text-white px-3 py-1 rounded" onClick={() => {
                const body = {
                  stripe_secret: document.getElementById("stripeKey").value,
                  stripe_account: document.getElementById("stripeID").value,
                  gumroad_token: document.getElementById("gumroadToken").value,
                  gumroad_user: document.getElementById("gumroadUser").value
                };
                fetch("http://127.0.0.1:8000/store-payment-keys", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify(body)
                }).then(res => res.json()).then(res => alert(res.message)).catch(() => alert("Failed to save payment credentials."));
              }}>Save Credentials</button>

              <div className="text-muted-foreground text-xs pt-2">Credentials will be stored locally and securely on this device only.</div>
            </CardContent>
          </Card>
        </TabsContent>

      <TabsContent value="ai">
          <Card>
            <CardContent className="p-4 space-y-4 text-sm">
              <div className="font-medium">OpenAI (ChatGPT)</div>
              <input id="openai" className="w-full p-2 border rounded text-xs" placeholder="OpenAI API Key" />

              <div className="font-medium pt-4">Anthropic (Claude)</div>
              <input id="claude" className="w-full p-2 border rounded text-xs" placeholder="Claude API Key" />

              <div className="font-medium pt-4">Google (Gemini)</div>
              <input id="gemini" className="w-full p-2 border rounded text-xs" placeholder="Gemini API Key (Google Cloud)" />

              <div className="font-medium pt-4">Grok (Placeholder)</div>
              <input id="grok" className="w-full p-2 border rounded text-xs" placeholder="Grok Auth Token" />

              <button className="text-xs bg-blue-600 text-white px-3 py-1 rounded" onClick={() => {
                const body = {
                  openai: document.getElementById("openai").value,
                  claude: document.getElementById("claude").value,
                  gemini: document.getElementById("gemini").value,
                  grok: document.getElementById("grok").value
                };
                fetch("http://127.0.0.1:8000/store-ai-keys", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify(body)
                }).then(res => res.json()).then(res => alert(res.message)).catch(() => alert("Failed to save keys."));
              }}>Save AI Keys</button>

              <div className="text-muted-foreground text-xs pt-2">Keys are stored locally and securely. You control which AIs Elysia can access.</div>
            </CardContent>
          </Card>
        </TabsContent>

      <TabsContent value="earnings">
          <Card>
            <CardContent className="p-4 text-sm">
              <div className="font-medium mb-2">Income Log</div>
              <EarningsLog />
            </CardContent>
          </Card>
        </TabsContent>

      <TabsContent value="projects">
          <Card>
            <CardContent className="p-4 text-sm space-y-2">
              <div className="font-medium mb-2">Project Contribution Ledger</div>
              <ProjectLedger />
            </CardContent>
          </Card>
        </TabsContent>

      <TabsContent value="project-income">
          <Card>
            <CardContent className="p-4 text-sm space-y-2">
              <div className="font-medium mb-2">Project Income Log</div>
              <ProjectIncome />
            </CardContent>
          </Card>
        </TabsContent>

      <TabsContent value="trust">
          <Card>
            <CardContent className="p-4 text-sm space-y-2">
              <div className="font-medium mb-2">Subnode Trust Scores</div>
              <TrustNetwork />
            </CardContent>
          </Card>
        </TabsContent>

      <TabsContent value="mutations">
          <Card>
            <CardContent className="p-4 text-sm space-y-2">
              <div className="font-medium mb-2">Pending Mutations</div>
              <MutationReview />
            </CardContent>
          </Card>
        </TabsContent>

      <TabsContent value="assignments">
          <Card>
            <CardContent className="p-4 text-sm space-y-2">
              <div className="font-medium mb-2">Task Assignment Log</div>
              <TaskRoutingLog />
            </CardContent>
          </Card>
        </TabsContent>

      <TabsContent value="credits">
          <Card>
            <CardContent className="p-4 text-sm space-y-2">
              <div className="font-medium mb-2">Redeem CoreCredits</div>
              <CoreCreditRedemption />
            </CardContent>
          </Card>
        </TabsContent>

      <TabsContent value="reputation">
          <Card>
            <CardContent className="p-4 text-sm space-y-2">
              <div className="font-medium mb-2">Reputation Tags</div>
              <ReputationTagList />
            </CardContent>
          </Card>
        </TabsContent>

      </Tabs>
    </div>
  );
}
