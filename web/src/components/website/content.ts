/** The approved website wording. The home, features and how-it-works pages are headings and buttons only (owner decision); the other pages keep their approved text word for word. */

export const HOME = {
  eyebrow: "CV screening",
  heading: "Shortlist the right people",
  rotatingWords: ["faster", "fairer", "smarter"],
  roles: [
    "Sales",
    "Nursing",
    "Finance",
    "Design",
    "Teaching",
    "Logistics",
    "Engineering",
    "Retail",
    "Hospitality",
    "Operations",
  ],
  steps: {
    kicker: "How it works",
    heading: { plain: "Three steps, ", marked: "one afternoon" },
    items: ["Upload CVs", "Bera scores each one", "You make the call"],
  },
  features: {
    kicker: "What you get",
    heading: { plain: "Everything a ", marked: "first pass", rest: " needs" },
    items: [
      "Every score explained",
      "Compare side by side",
      "Filters that get specific",
      "Shareable reports",
      "Built for teams",
      "Data you control",
    ],
  },
  closing: { plain: "Ready to read less and ", marked: "decide better?" },
} as const;

export const HOW_IT_WORKS = {
  heading: "How it works",
  steps: ["Create a project", "Upload CVs", "Get scores", "Compare and decide"],
  closing: { plain: "Start with ", marked: "your first project" },
} as const;

export const FEATURES = {
  heading: "Features",
  items: [
    "Job projects",
    "Bulk CV upload",
    "AI scoring",
    "Explanation",
    "Ranked comparison",
    "Filters",
    "Candidate stages",
    "Top candidate reports",
    "Team access",
    "Usage tracking",
    "Data privacy controls",
  ],
  trust: {
    kicker: "Why teams trust it",
    heading: { plain: "Built for a ", marked: "fair", rest: " first pass" },
    items: ["You stay in charge", "Every score explained", "Your data, your rules"],
  },
  closing: { plain: "Try it on your ", marked: "next role" },
} as const;

export const FAQ = {
  heading: "FAQ",
  subheading: "Short answers to common questions.",
  questions: [
    {
      question: "What is Bera?",
      answer:
        "Bera is a tool that scores and ranks CVs against the requirements of a job opening, so hiring teams can shortlist faster.",
    },
    {
      question: "Which file types can I upload?",
      answer: "PDF and Word (DOCX) files. You can upload many at once.",
    },
    {
      question: "Can I add more CVs later?",
      answer: "Yes. New CVs join the comparison for that job automatically.",
    },
    {
      question: "How does the scoring work?",
      answer:
        "You decide what is a must have and what is nice to have. Bera checks each CV against those points and explains the result.",
    },
    {
      question: "Who makes the final decision?",
      answer: "You do. Bera gives a guide, and the recruiter always has the last word.",
    },
    {
      question: "Can my team use it?",
      answer:
        "Yes. You can invite a few colleagues to your account, and each person gets their own login.",
    },
    {
      question: "What happens to candidate data?",
      answer: "You choose how long it is kept. After that, it is deleted automatically.",
    },
  ],
  closing: "Have another question?",
  closingLink: "Our team will be happy to help.",
} as const;

/** Shown while a legal page has no text: the wording comes from the owner after legal review. */
export const LEGAL_PREPARING = "This page is being prepared";

/** The public chat's labels. The owner supplies any other wording. */
export const CHAT = {
  barLabel: "Ask a question",
  askButton: "Ask",
  launcher: "Chat",
  windowLabel: "Chat",
  newChat: "New chat",
  chatsHeading: "Chats",
  chatsToggle: "Chats",
  message: "Message",
  send: "Send",
  close: "Close",
  thinking: "Thinking",
  you: "You",
  assistant: "Assistant",
} as const;
