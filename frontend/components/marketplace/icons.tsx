import {
  LifeBuoy, MessageSquareHeart, UtensilsCrossed, ChefHat, Stethoscope, HeartPulse,
  GraduationCap, BookOpen, ShoppingBag, ShoppingCart, Landmark, HandCoins,
  Users, UserPlus, BedDouble, ConciergeBell, Plane, Luggage, Home, KeyRound,
  Briefcase, Building2, Sparkles, HelpCircle, Store, Bot, type LucideIcon,
} from 'lucide-react'

const ICONS: Record<string, LucideIcon> = {
  LifeBuoy, MessageSquareHeart, UtensilsCrossed, ChefHat, Stethoscope, HeartPulse,
  GraduationCap, BookOpen, ShoppingBag, ShoppingCart, Landmark, HandCoins,
  Users, UserPlus, BedDouble, ConciergeBell, Plane, Luggage, Home, KeyRound,
  Briefcase, Building2, Sparkles, HelpCircle, Store, Bot,
}

export function TemplateIcon({ name, size = 16, className }: { name: string; size?: number; className?: string }) {
  const Icon = ICONS[name] || Bot
  return <Icon size={size} className={className} />
}
