/** The approved website wording, word for word. Change it only when the owner approves new text. */

export const HOME = {
  heading: "Bera",
  subheading:
    "Upload CVs in bulk. Bera scores each one against your job requirements and ranks the best candidates.",
  sections: [
    {
      title: "What Bera is",
      text: "Bera helps hiring teams get through a pile of CVs without the usual stress. You create a project for a job, upload the CVs, and Bera shows who fits best.",
    },
    {
      title: "Who it helps",
      text: "Recruiters, HR teams, small businesses and growing companies. Anyone who reads many applications for one role and wants a clear, fair first pass.",
    },
    {
      title: "You stay in charge",
      text: "Bera supports your decision and does not make it. The final call always stays with the recruiter.",
    },
  ],
} as const;

export const HOW_IT_WORKS = {
  heading: "How it works",
  steps: [
    {
      title: "Create a project.",
      text: "Add a job description, and set what is a must have and what is nice to have.",
    },
    {
      title: "Upload CVs.",
      text: "Add many PDF or Word files at once. You can add more later.",
    },
    {
      title: "Get scores.",
      text: "Every candidate receives a score and a short explanation, based on what is in the CV.",
    },
    {
      title: "Compare and decide.",
      text: "See everyone ranked on one dashboard, filter the list, and share your top picks.",
    },
  ],
} as const;

export const FEATURES = {
  heading: "Features",
  items: [
    {
      name: "Job projects",
      does: "Gives every job opening its own space.",
      helps: "Keeps candidates for different roles neatly apart.",
    },
    {
      name: "Bulk CV upload",
      does: "Lets you add many PDF or Word CVs together.",
      helps: "Saves the time of opening files one by one.",
    },
    {
      name: "AI scoring",
      does: "Checks each CV against what the job needs.",
      helps: "Gives you a fair first pass in minutes.",
    },
    {
      name: "Explanation",
      does: "Shows why a candidate got their score.",
      helps: "You can trust the result and explain it to others.",
    },
    {
      name: "Ranked comparison",
      does: "Puts all candidates side by side, best first.",
      helps: "Makes it easy to spot the strongest people.",
    },
    {
      name: "Filters",
      does: "Narrows the list by score or missing skills.",
      helps: "Helps you find exactly who you are looking for.",
    },
    {
      name: "Candidate stages",
      does: "Lets you mark people as shortlisted, interview, approved or rejected.",
      helps: "Keeps the hiring process organised in one place.",
    },
    {
      name: "Top candidate reports",
      does: "Lets you share or export your best picks.",
      helps: "Makes it simple to update managers and colleagues.",
    },
    {
      name: "Team access",
      does: "Lets you invite colleagues to your account.",
      helps: "Everyone works from the same information.",
    },
    {
      name: "Usage tracking",
      does: "Shows how many CVs you have used.",
      helps: "No surprises with your plan limits.",
    },
    {
      name: "Data privacy controls",
      does: "Lets you choose how long candidate data is kept.",
      helps: "Old data is removed when you no longer need it.",
    },
  ],
} as const;
