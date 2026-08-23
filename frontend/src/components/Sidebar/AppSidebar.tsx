import {
  Briefcase,
  History,
  Home,
  MessageSquareText,
  ReceiptText,
  SlidersHorizontal,
  Smartphone,
  Users,
} from "lucide-react"

import { SidebarAppearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
} from "@/components/ui/sidebar"
import useAuth from "@/hooks/useAuth"
import { type Item, Main } from "./Main"
import { User } from "./User"

const baseItems: Item[] = [
  { icon: Home, title: "Dashboard", path: "/" },
  { icon: Briefcase, title: "Items", path: "/items" },
]

export function AppSidebar() {
  const { user: currentUser } = useAuth()

  const items = currentUser?.is_superuser
    ? [
        ...baseItems,
        { icon: Users, title: "Admin", path: "/admin" },
        { icon: Smartphone, title: "App Users", path: "/app-users" },
        {
          icon: MessageSquareText,
          title: "App Contents",
          path: "/app-contents",
        },
        { icon: ReceiptText, title: "App Orders", path: "/app-orders" },
        {
          icon: SlidersHorizontal,
          title: "App Configs",
          path: "/app-configs",
        },
        { icon: History, title: "App Logs", path: "/app-operation-logs" },
      ]
    : baseItems

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="px-4 py-6 group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:items-center">
        <Logo variant="responsive" />
      </SidebarHeader>
      <SidebarContent>
        <Main items={items} />
      </SidebarContent>
      <SidebarFooter>
        <SidebarAppearance />
        <User user={currentUser} />
      </SidebarFooter>
    </Sidebar>
  )
}

export default AppSidebar
