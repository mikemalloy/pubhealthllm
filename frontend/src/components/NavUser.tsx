"use client";

import { useUser, useClerk, SignInButton } from "@clerk/nextjs";
import { ChevronsUpDown, LogIn } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";

function initials(name: string | null | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(" ");
  if (parts.length === 1) return (parts[0][0] ?? "?").toUpperCase();
  return ((parts[0][0] ?? "") + (parts[parts.length - 1][0] ?? "")).toUpperCase();
}

export default function NavUser() {
  const { isLoaded, isSignedIn, user } = useUser();
  const { openUserProfile, signOut } = useClerk();
  const { isMobile } = useSidebar();

  // While Clerk is loading, render nothing to avoid flicker
  if (!isLoaded) return null;

  // ── Signed out ──────────────────────────────────────────────────────────────
  if (!isSignedIn) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SignInButton mode="modal">
            <SidebarMenuButton size="lg">
              <LogIn className="h-4 w-4" />
              <span>Sign in</span>
            </SidebarMenuButton>
          </SignInButton>
        </SidebarMenuItem>
      </SidebarMenu>
    );
  }

  // ── Signed in ───────────────────────────────────────────────────────────────
  const name = user.fullName ?? user.firstName ?? "User";
  const email = user.primaryEmailAddress?.emailAddress ?? "";
  const imageUrl = user.imageUrl;
  const abbr = initials(name);

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
            >
              <Avatar className="h-8 w-8 rounded-lg">
                {imageUrl && <AvatarImage src={imageUrl} alt={name} />}
                <AvatarFallback className="rounded-lg">{abbr}</AvatarFallback>
              </Avatar>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">{name}</span>
                <span className="truncate text-xs text-muted-foreground">{email}</span>
              </div>
              <ChevronsUpDown className="ml-auto h-4 w-4 shrink-0" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>

          <DropdownMenuContent
            className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
            side={isMobile ? "bottom" : "right"}
            align="end"
            sideOffset={4}
          >
            {/* Header row: avatar + name + email */}
            <DropdownMenuLabel className="p-0 font-normal">
              <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                <Avatar className="h-8 w-8 rounded-lg">
                  {imageUrl && <AvatarImage src={imageUrl} alt={name} />}
                  <AvatarFallback className="rounded-lg">{abbr}</AvatarFallback>
                </Avatar>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">{name}</span>
                  <span className="truncate text-xs text-muted-foreground">{email}</span>
                </div>
              </div>
            </DropdownMenuLabel>

            <DropdownMenuSeparator />

            <DropdownMenuItem onSelect={() => openUserProfile()}>
              Manage account
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => signOut()}>
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
