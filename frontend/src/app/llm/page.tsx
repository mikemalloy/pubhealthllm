import { auth } from "@clerk/nextjs/server";
import LlmChat from "@/components/LlmChat";

export default async function LlmPage() {
  await auth(); // Clerk middleware already protects this route; belt-and-suspenders.
  return <LlmChat />;
}
