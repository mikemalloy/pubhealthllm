import { auth } from "@clerk/nextjs/server";
import { MessageSquare } from "lucide-react";

export default async function LlmPage() {
  const { userId } = await auth();

  return (
    <div className="flex flex-1 flex-col items-center justify-center min-h-[60vh] gap-4 text-center">
      <div className="rounded-full bg-primary/10 p-4">
        <MessageSquare className="h-8 w-8 text-primary" />
      </div>
      <h1 className="text-2xl font-semibold tracking-tight">Pub Health LLM</h1>
      <p className="text-muted-foreground max-w-sm">
        AI-powered public health analytics — CDC PLACES, MMWR surveillance, and
        decision support. Coming soon.
      </p>
      <p className="text-xs text-muted-foreground/60">Signed in as user {userId}</p>
    </div>
  );
}
