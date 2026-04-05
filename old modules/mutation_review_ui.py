import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const API = "http://localhost:3001/api/mutations";

export default function MutationReviewTab() {
  const [queue, setQueue] = useState([]);

  const fetchQueue = async () => {
    const res = await fetch(`${API}/review`);
    setQueue(await res.json());
  };

  const approve = async (id) => {
    await fetch(`${API}/${id}/approve`, { method: "POST" });
    fetchQueue();
  };

  const reject = async (id) => {
    await fetch(`${API}/${id}/reject`, { method: "POST" });
    fetchQueue();
  };

  useEffect(() => {
    fetchQueue();
  }, []);

  return (
    <div className="grid gap-4 p-4">
      <h2 className="text-xl font-semibold">Mutation Review Queue</h2>
      {queue.length === 0 ? (
        <p>No pending mutations.</p>
      ) : (
        queue.map((mut, index) => (
          <Card key={index}>
            <CardContent>
              <p><strong>ID:</strong> {mut.mutation_id}</p>
              <p><strong>Author:</strong> {mut.author}</p>
              <p><strong>Trust Score:</strong> {mut.trust_score}</p>
              <pre className="bg-gray-100 p-2 mt-2 rounded text-sm overflow-auto">
                {mut.code}
              </pre>
              <div className="flex gap-2 mt-4">
                <Button onClick={() => approve(mut.mutation_id)}>Approve</Button>
                <Button variant="destructive" onClick={() => reject(mut.mutation_id)}>Reject</Button>
              </div>
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}
