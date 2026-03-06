# 🚀 Connecteam Theme - Quick Start Guide

## For Developers - Get Started in 5 Minutes

### 1. Understand the Components (2 min)

Your new UI kit has 6 main components:

```tsx
// File: dashboard/components/ConnecteamUIKit.tsx

PrimaryButton      // Main blue CTA button
SecondaryButton    // Gray outline button
FeatureCard        // Icon + Title + Description card
StatCard           // Metric card with optional trend
SectionHeader      // Section title with optional action
Badge              // Tag/label with variants
```

### 2. Import in Your Page (1 min)

```tsx
'use client';

import { 
  PrimaryButton, 
  FeatureCard,
  StatCard,
  SectionHeader 
} from '@/components/ConnecteamUIKit';

import { Zap, Users, BarChart3 } from 'lucide-react';
```

### 3. Use in Your Code (2 min)

**Button:**
```tsx
<PrimaryButton onClick={() => alert('Clicked!')}>
  Get Started
</PrimaryButton>
```

**Feature:**
```tsx
<FeatureCard
  icon={Zap}
  title="Fast Setup"
  description="Deploy in minutes"
/>
```

**Metric:**
```tsx
<StatCard
  label="Active Users"
  value="1,234"
  icon={Users}
/>
```

**Section:**
```tsx
<SectionHeader 
  title="Dashboard"
  description="Your overview"
/>
```

---

## CSS Classes You'll Use

### Colors (Text)
```tsx
className="text-foreground"        // Black text
className="text-muted-foreground"  // Gray text
className="text-primary"           // Blue text
className="text-secondary"         // Teal text
```

### Colors (Background)
```tsx
className="bg-primary"      // Blue background
className="bg-secondary"    // Teal background
className="bg-background"   // White background
```

### Spacing
```tsx
className="p-4"    // Padding all sides
className="mb-6"   // Bottom margin
className="gap-4"  // Flex/grid gap
```

### Cards
```tsx
className="card-elevated"  // Elevated card effect
className="rounded-lg"     // Rounded corners
className="shadow-lg"      // Big shadow
```

---

## Layout Patterns

### Hero Section
```tsx
<div className="text-center py-16">
  <h1 className="text-5xl font-bold text-foreground mb-4">
    Your Title
  </h1>
  <p className="text-xl text-muted-foreground mb-8">
    Your description
  </p>
  <PrimaryButton size="lg">Get Started</PrimaryButton>
</div>
```

### Features Grid
```tsx
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
  <FeatureCard icon={Zap} title="Feature 1" description="Desc" />
  <FeatureCard icon={Shield} title="Feature 2" description="Desc" />
  <FeatureCard icon={Users} title="Feature 3" description="Desc" />
</div>
```

### Stats Grid
```tsx
<div className="grid grid-cols-2 md:grid-cols-4 gap-4">
  <StatCard label="Users" value="1.2K" icon={Users} />
  <StatCard label="Revenue" value="$50K" icon={TrendingUp} />
  <StatCard label="Growth" value="+23%" icon={BarChart3} />
  <StatCard label="Uptime" value="99.9%" icon={Shield} />
</div>
```

### Feature + Text
```tsx
<div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
  <div>
    <h2 className="text-4xl font-bold mb-6">Benefits</h2>
    <ul className="space-y-4">
      <li className="flex items-start gap-3">
        <CheckCircle2 className="h-6 w-6 text-secondary" />
        <span>Benefit 1</span>
      </li>
    </ul>
  </div>
  <div className="grid grid-cols-2 gap-4">
    <StatCard label="Stat 1" value="100" />
  </div>
</div>
```

---

## Color Reference

| Color | Tailwind Class | Hex |
|-------|---------------|-----|
| Primary Blue | `text-primary` / `bg-primary` | #4A9EFF |
| Secondary Teal | `text-secondary` / `bg-secondary` | #06DDB8 |
| Dark Text | `text-foreground` | #1F2937 |
| Light Text | `text-muted-foreground` | #6B7280 |
| Light Gray | `bg-gray-100` | #F3F4F6 |
| Dark Gray | `bg-gray-800` | #1F2937 |

---

## Common Tasks

### Make a Page
```tsx
'use client';

import { SectionHeader, PrimaryButton, FeatureCard } from '@/components/ConnecteamUIKit';

export default function MyPage() {
  return (
    <div className="min-h-screen bg-background">
      <SectionHeader 
        title="My Page"
        description="What this page does"
      />
      
      <div className="grid grid-cols-3 gap-6">
        <FeatureCard 
          icon={/* icon */}
          title="Feature"
          description="Desc"
        />
      </div>
    </div>
  );
}
```

### Update a Button
```tsx
// Before
<button className="bg-blue-500 text-white px-4 py-2">
  Click
</button>

// After
<PrimaryButton>Click</PrimaryButton>
```

### Update a Card
```tsx
// Before
<div className="rounded-lg shadow p-4 bg-white">Content</div>

// After
<div className="card-elevated">Content</div>
```

---

## Responsive Breakpoints

```tsx
// 1 column (mobile)
<div className="grid grid-cols-1">

// 2 columns on tablet and up
<div className="grid grid-cols-1 md:grid-cols-2">

// 3 columns on desktop and up
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3">

// 4 columns on large screens
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4">
```

---

## Dark Mode

Dark mode is automatic, but you can test it:

```tsx
// In your layout.tsx
<html className="dark">  {/* Add 'dark' class to test */}

// Dark mode versions of components work automatically
// All colors have light/dark variants defined
```

---

## Quick Checklist

Before shipping a page:

- [ ] Used `PrimaryButton` for main CTAs
- [ ] Used `SecondaryButton` for alternatives
- [ ] Applied `card-elevated` to cards
- [ ] Used `FeatureCard` for features
- [ ] Used `SectionHeader` for sections
- [ ] Colors use `text-primary`, `bg-primary`, etc.
- [ ] Spacing uses scale (4, 8, 12, 16, 24, 32, 48px)
- [ ] Tested on mobile (375px wide)
- [ ] Tested dark mode
- [ ] Checked keyboard navigation (Tab key)

---

## Files You'll Reference

```
dashboard/
  ├── components/
  │   ├── ConnecteamUIKit.tsx      ← Component library
  │   └── ConnecteamWelcome.tsx    ← Example page
  ├── lib/
  │   └── design-system.ts         ← Design constants
  ├── app/
  │   └── globals.css              ← Theme colors
  ├── CONNECTEAM_THEME_UPDATE.md   ← Full guide
  ├── MIGRATION_GUIDE.md           ← Update pages
  └── CONNECTEAM_VISUAL_REFERENCE.md ← Design specs
```

---

## Need Help?

### Component Usage?
→ Check `CONNECTEAM_THEME_UPDATE.md`

### How to update a page?
→ Follow `MIGRATION_GUIDE.md`

### Design specs?
→ See `CONNECTEAM_VISUAL_REFERENCE.md`

### Code examples?
→ View `components/ConnecteamWelcome.tsx`

---

## 3 Simple Rules

1. **Use Components** - Import from `ConnecteamUIKit.tsx`
2. **Use Colors** - Use Tailwind classes (`text-primary`, `bg-primary`)
3. **Use Spacing** - Stick to scale (4, 8, 12, 16, 24, 32, 48px)

That's it! 🎉

---

## Example Page (Copy & Paste)

```tsx
'use client';

import { 
  PrimaryButton, 
  SectionHeader, 
  FeatureCard,
  StatCard 
} from '@/components/ConnecteamUIKit';

import { Zap, Shield, Users } from 'lucide-react';

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Hero */}
      <section className="px-4 py-16 text-center max-w-6xl mx-auto">
        <h1 className="text-5xl font-bold text-foreground mb-4">
          Welcome to Your Dashboard
        </h1>
        <p className="text-xl text-muted-foreground mb-8">
          Manage everything in one place
        </p>
        <PrimaryButton size="lg">Get Started</PrimaryButton>
      </section>

      {/* Stats */}
      <section className="px-4 py-12 max-w-6xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatCard label="Users" value="1.2K" icon={Users} />
          <StatCard label="Revenue" value="$50K" icon={Zap} />
          <StatCard label="Growth" value="+23%" icon={Shield} />
          <StatCard label="Uptime" value="99.9%" icon={Zap} />
        </div>
      </section>

      {/* Features */}
      <section className="px-4 py-12 max-w-6xl mx-auto">
        <SectionHeader 
          title="Features"
          description="Everything you need"
        />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <FeatureCard 
            icon={Zap} 
            title="Fast" 
            description="Lightning quick setup" 
          />
          <FeatureCard 
            icon={Shield} 
            title="Secure" 
            description="Bank-level security" 
          />
          <FeatureCard 
            icon={Users} 
            title="Team" 
            description="Collaborate easily" 
          />
        </div>
      </section>
    </div>
  );
}
```

Copy this, update it with your content, and you're done! ✨

---

**Need more?** Read `CONNECTEAM_THEME_UPDATE.md` for the complete guide.

Happy building! 🚀
