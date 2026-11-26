"use client";

import { ChatShell } from "@/components/chat/ChatShell";
import { chatTitle } from "@/lib/publicChat";

import { CHAT } from "../content";
import type { ChatSession } from "./ChatProvider";

/** The public chat's window: answers are shown as plain text. */
export function ChatWindow({ session, onClose }: { session: ChatSession; onClose: () => void }) {
  const active = session.chats.find((chat) => chat.id === session.activeId);
  return (
    <ChatShell
      labels={CHAT}
      items={session.chats.map((chat) => ({
        id: chat.id,
        title: chatTitle(chat),
        current: chat.id === session.activeId,
      }))}
      onNewChat={session.startNew}
      onSelect={session.select}
      onClose={onClose}
      onSend={(text) => session.send(text)}
      asking={session.asking}
      maxLength={session.maxQuestionLength}
      scrollKey={active?.messages.length ?? 0}
    >
      {active?.messages.map((message, index) => (
        <div key={index} className={`chat-window__message chat-window__message--${message.role}`}>
          <span className="chat-window__who">
            {message.role === "user" ? CHAT.you : CHAT.assistant}
          </span>
          <p>{message.text}</p>
        </div>
      ))}
      {session.asking ? <p className="chat-window__status">{CHAT.thinking}</p> : null}
      {session.error ? (
        <p className="chat-window__error" role="alert">
          {session.error}
        </p>
      ) : null}
    </ChatShell>
  );
}
