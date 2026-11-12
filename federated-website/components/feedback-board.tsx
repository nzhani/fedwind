"use client"

// Feedback form and public discussion board (moved out of the legacy dashboard page).
// Talks to the legacy /api/feedback endpoints through lib/api.ts.

import React from "react"
import { useState, useEffect } from "react"
import {
  submitFeedback,
  getPublicAnswers,
  getFeedbackMessages,
  createFeedbackFollowUp,
  type PublicAnswerItem,
  type ConversationMessageItem,
} from "@/lib/api"
import { Button } from "@/components/ui/button"
import { CheckCircle2, MessageSquare, RefreshCw, Send } from "lucide-react"

export function FeedbackBoard() {
  // Feedback state
  const [feedbackMessage, setFeedbackMessage] = useState("")
  const [feedbackName, setFeedbackName] = useState("")
  const [sendingFeedback, setSendingFeedback] = useState(false)
  const [feedbackSent, setFeedbackSent] = useState(false)

  // Public answers state
  const [publicAnswers, setPublicAnswers] = useState<PublicAnswerItem[]>([])
  const [loadingPublicAnswers, setLoadingPublicAnswers] = useState(false)
  const [currentAnswersPage, setCurrentAnswersPage] = useState(1)
  const [expandedConversationId, setExpandedConversationId] = useState<string | null>(null)
  const [loadingConversationId, setLoadingConversationId] = useState<string | null>(null)
  const [conversationMessages, setConversationMessages] = useState<Record<string, ConversationMessageItem[]>>({})
  const [replyConversationId, setReplyConversationId] = useState<string | null>(null)
  const [replyToMessageId, setReplyToMessageId] = useState<string | null>(null)
  const [followUpMessage, setFollowUpMessage] = useState("")
  const [followUpName, setFollowUpName] = useState("")
  const [sendingFollowUp, setSendingFollowUp] = useState(false)
  const [expandedReplyChildren, setExpandedReplyChildren] = useState<Record<string, boolean>>({})
  const ANSWERS_PER_PAGE = 5
  const [error, setError] = useState<string | null>(null)

  // Submit feedback
  const handleSubmitFeedback = async () => {
    if (!feedbackMessage.trim()) return
    
    setError(null)
    setSendingFeedback(true)
    try {
      await submitFeedback(
        feedbackMessage.trim(),
        feedbackName.trim() || undefined,
        "dashboard",
      )
      setFeedbackMessage("")
      setFeedbackName("")
      setFeedbackSent(true)
      setTimeout(() => setFeedbackSent(false), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send feedback")
    } finally {
      setSendingFeedback(false)
    }
  }

  const loadPublicAnswers = async () => {
    setLoadingPublicAnswers(true)
    try {
      const result = await getPublicAnswers()
      setPublicAnswers(result.entries)
      setCurrentAnswersPage(1)

      const loadedConversations = await Promise.all(
        result.entries.map(async (entry) => {
          try {
            const conversation = await getFeedbackMessages(entry.id)
            return [entry.id, conversation.entries] as const
          } catch {
            return [entry.id, []] as const
          }
        }),
      )

      setConversationMessages((prev) => ({
        ...prev,
        ...Object.fromEntries(loadedConversations),
      }))
    } catch (err) {
      console.error("[v0] Failed to load public answers:", err)
    } finally {
      setLoadingPublicAnswers(false)
    }
  }

  const loadConversationMessages = async (conversationId: string) => {
    setLoadingConversationId(conversationId)
    try {
      const result = await getFeedbackMessages(conversationId)
      setConversationMessages((prev) => ({
        ...prev,
        [conversationId]: result.entries,
      }))
      return result.entries
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversation")
      return []
    } finally {
      setLoadingConversationId(null)
    }
  }

  const toggleConversationThread = async (conversationId: string) => {
    if (expandedConversationId === conversationId) {
      setExpandedConversationId(null)

      if (replyConversationId === conversationId) {
        setReplyConversationId(null)
        setReplyToMessageId(null)
        setFollowUpMessage("")
        setFollowUpName("")
      }
      return
    }

    setExpandedConversationId(conversationId)

    if (!conversationMessages[conversationId]) {
      await loadConversationMessages(conversationId)
    }
  }

  const getVisibleMessages = (conversationId: string) => {
    const messages = conversationMessages[conversationId] ?? []
    return messages.filter(
      (message) => message.sender_type === "user" || message.is_public,
    )
  }

  const getThreadRootQuestionMessage = (conversationId: string) => {
    const messages = conversationMessages[conversationId] ?? []
    return messages.find((message) => message.sender_type === "user") ?? null
  }

  const getMainOfficialAnswerMessage = (conversationId: string) => {
    const rootQuestion = getThreadRootQuestionMessage(conversationId)
    if (!rootQuestion) return null

    const messages = conversationMessages[conversationId] ?? []
    const matches = messages
      .filter(
        (message) =>
          message.sender_type === "developer" &&
          message.is_public &&
          message.reply_to_message_id === rootQuestion.id,
      )
      .sort(
        (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      )

    return matches.length > 0 ? matches[matches.length - 1] : null
  }

  const getMainUserAnswerMessage = (conversationId: string) => {
    const rootQuestion = getThreadRootQuestionMessage(conversationId)
    if (!rootQuestion) return null

    const messages = getVisibleMessages(conversationId)
      .filter(
        (message) =>
          message.sender_type === "user" &&
          message.id !== rootQuestion.id &&
          message.reply_to_message_id === rootQuestion.id,
      )
      .sort(
        (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      )

    return messages.length > 0 ? messages[0] : null
  }

  const findMessageById = (conversationId: string, messageId: string | null) => {
    if (!messageId) return null
    const messages = conversationMessages[conversationId] ?? []
    return messages.find((message) => message.id === messageId) ?? null
  }

  const getMessageElementId = (messageId: string) => `thread-message-${messageId}`

  const scrollToMessage = (messageId: string | null) => {
    if (!messageId) return

    const element = document.getElementById(getMessageElementId(messageId))
    if (!element) return

    element.scrollIntoView({ behavior: "smooth", block: "center" })

    element.classList.add(
      "rounded-md",
      "bg-yellow-100/60",
      "ring-1",
      "ring-yellow-300/60",
      "transition-all",
      "duration-300"
    )

    window.setTimeout(() => {
      element.classList.remove(
        "rounded-md",
        "bg-yellow-100/60",
        "ring-1",
        "ring-yellow-300/60",
        "transition-all",
        "duration-300"
      )
    }, 900)
  }

  const getReplyPreviewText = (conversationId: string, replyToMessageId: string | null) => {
    const targetMessage = findMessageById(conversationId, replyToMessageId)
    if (!targetMessage) return "Earlier message"

    const text = targetMessage.message_text.trim()
    if (text.length <= 60) return text
    return `${text.slice(0, 60)}...`
  }

  const openReplyFormForQuestion = async (conversationId: string) => {
    let messages = conversationMessages[conversationId]

    if (!messages) {
      setExpandedConversationId(conversationId)
      messages = await loadConversationMessages(conversationId)
    } else if (expandedConversationId !== conversationId) {
      setExpandedConversationId(conversationId)
    }

    const rootQuestion =
      messages?.find((message) => message.sender_type === "user") ?? null

    if (!rootQuestion) {
      setError("Could not find the main question to reply to.")
      return
    }

    setReplyConversationId(conversationId)
    setReplyToMessageId(rootQuestion.id)
  }

  const openReplyFormForMessage = async (conversationId: string, messageId: string) => {
    if (expandedConversationId !== conversationId) {
      setExpandedConversationId(conversationId)
    }

    if (!conversationMessages[conversationId]) {
      await loadConversationMessages(conversationId)
    }

    setReplyConversationId(conversationId)
    setReplyToMessageId(messageId)
  }

  const closeReplyForm = () => {
    setReplyConversationId(null)
    setReplyToMessageId(null)
    setFollowUpMessage("")
    setFollowUpName("")
  }

  const handleSubmitFollowUp = async () => {
    if (!replyConversationId || !replyToMessageId || !followUpMessage.trim()) return

    setSendingFollowUp(true)
    try {
      await createFeedbackFollowUp(
        replyConversationId,
        followUpMessage.trim(),
        followUpName.trim() || undefined,
        "dashboard",
        replyToMessageId,
      )

      const conversationId = replyConversationId
      closeReplyForm()
      setExpandedConversationId(conversationId)
      await loadConversationMessages(conversationId)
      await loadPublicAnswers()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send follow-up")
    } finally {
      setSendingFollowUp(false)
    }
  }

  const getTopLevelThreadMessages = (conversationId: string) => {
    const visibleMessages = getVisibleMessages(conversationId)
    const rootQuestion = getThreadRootQuestionMessage(conversationId)
    const mainOfficialAnswer = getMainOfficialAnswerMessage(conversationId)

    if (!rootQuestion) return []

    return visibleMessages
      .filter((message) => {
        if (message.id === rootQuestion.id) return false
        if (mainOfficialAnswer && message.id === mainOfficialAnswer.id) return false
        if (!message.reply_to_message_id) return false

        return (
          message.reply_to_message_id === rootQuestion.id ||
          (mainOfficialAnswer && message.reply_to_message_id === mainOfficialAnswer.id)
        )
      })
      .sort(
        (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      )
  }

  const getChildThreadMessages = (conversationId: string, parentMessageId: string) => {
    const visibleMessages = getVisibleMessages(conversationId)

    return visibleMessages
      .filter((message) => message.reply_to_message_id === parentMessageId)
      .sort(
        (a, b) =>
          new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
      )
  }

  const getOrphanPublicReplies = (conversationId: string) => {
    const visibleMessages = getVisibleMessages(conversationId)
    const rootQuestion = getThreadRootQuestionMessage(conversationId)
    const mainOfficialAnswer = getMainOfficialAnswerMessage(conversationId)
    const validParentIds = new Set(visibleMessages.map((message) => message.id))

    return visibleMessages.filter((message) => {
      if (!(message.sender_type === "developer" && message.is_public)) {
        return false
      }

      if (!message.reply_to_message_id) {
        return false
      }

      if (rootQuestion && message.reply_to_message_id === rootQuestion.id) {
        return false
      }

      if (mainOfficialAnswer && message.reply_to_message_id === mainOfficialAnswer.id) {
        return false
      }

      return !validParentIds.has(message.reply_to_message_id)
    })
  }

  const toggleReplyChildren = (messageId: string) => {
    setExpandedReplyChildren((prev) => ({
      ...prev,
      [messageId]: !prev[messageId],
    }))
  } 


  const renderReplyForm = (conversationId: string, messageId: string) => {
    const isOpen =
      replyConversationId === conversationId && replyToMessageId === messageId

    if (!isOpen) return null

    return (
      <div className="mt-3 rounded-lg border border-border bg-background p-4 space-y-4">
        <div>
          <label className="text-sm font-medium text-foreground block mb-2">
            Your Name (optional)
          </label>
          <input
            type="text"
            value={followUpName}
            onChange={(e) => setFollowUpName(e.target.value)}
            placeholder="Enter your name or leave blank for anonymous"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
          />
        </div>

        <div>
          <label className="text-sm font-medium text-foreground block mb-2">
            Reply
          </label>
          <textarea
            value={followUpMessage}
            onChange={(e) => setFollowUpMessage(e.target.value)}
            placeholder="Write your reply here..."
            className="w-full rounded-md border border-input bg-background px-3 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 resize-vertical min-h-24"
          />
        </div>

        <div className="flex justify-end gap-2">
          <Button
            variant="outline"
            onClick={closeReplyForm}
            disabled={sendingFollowUp}
          >
            Cancel
          </Button>

          <Button
            onClick={handleSubmitFollowUp}
            disabled={sendingFollowUp || !followUpMessage.trim()}
            className="gap-2"
          >
            {sendingFollowUp ? (
              <>
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-background border-t-transparent" />
                Sending...
              </>
            ) : (
              <>
                <Send className="h-4 w-4" />
                Send Reply
              </>
            )}
          </Button>
        </div>
      </div>
    )
  }

const renderConversationNode = (
  conversationId: string,
  message: ConversationMessageItem,
  depth = 0,
): React.ReactNode => {
  const childMessages = getChildThreadMessages(conversationId, message.id)
  const hasChildren = childMessages.length > 0
  const showChildren = expandedReplyChildren[message.id] ?? false

  return (
    <div
      key={message.id}
      className={depth > 0 ? "ml-6 border-l border-border pl-4 space-y-3" : "space-y-3"}
    >
      <div
        id={getMessageElementId(message.id)}
        className={`rounded-md border p-3 ${
          message.sender_type === "developer"
            ? "border-primary/20 bg-primary/5"
            : "border-border bg-muted/20"
        }`}
      >
        <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>
            {message.sender_type === "developer"
              ? "Official Reply"
              : message.sender_name || "User"}{" "}
            • {new Date(message.created_at).toLocaleString()}
          </span>

          {message.reply_to_message_id && (
            <button
              type="button"
              onClick={() => scrollToMessage(message.reply_to_message_id)}
              className="italic underline underline-offset-2 hover:text-foreground"
            >
              Re: {getReplyPreviewText(conversationId, message.reply_to_message_id)}
            </button>
          )}
        </div>

        <p className="text-sm text-foreground whitespace-pre-wrap">
          {message.message_text}
        </p>

        <div className="mt-2 flex flex-wrap items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => openReplyFormForMessage(conversationId, message.id)}
            className="h-auto p-0 text-xs font-bold text-muted-foreground hover:bg-transparent hover:text-foreground"
          >
            Reply
          </Button>

          {hasChildren && (
            <button
              type="button"
              onClick={() => toggleReplyChildren(message.id)}
              className="text-xs font-medium text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              {showChildren
                ? `Hide replies (${childMessages.length})`
                : `Show replies (${childMessages.length})`}
            </button>
          )}
        </div>

        {renderReplyForm(conversationId, message.id)}
      </div>

      {hasChildren && showChildren && (
        <div className="space-y-3">
          {childMessages.map((childMessage) =>
            renderConversationNode(conversationId, childMessage, depth + 1),
          )}
        </div>
      )}
    </div>
  )
}


  const totalAnswerPages = Math.max(1, Math.ceil(publicAnswers.length / ANSWERS_PER_PAGE))
  const startAnswerIndex = (currentAnswersPage - 1) * ANSWERS_PER_PAGE
  const endAnswerIndex = startAnswerIndex + ANSWERS_PER_PAGE
  const visiblePublicAnswers = publicAnswers.slice(startAnswerIndex, endAnswerIndex)

  const answerPageNumbers = Array.from({ length: totalAnswerPages }, (_, i) => i + 1)


  useEffect(() => {
    loadPublicAnswers()
  }, [])

  useEffect(() => {
    if (currentAnswersPage > totalAnswerPages) {
      setCurrentAnswersPage(totalAnswerPages)
    }
  }, [currentAnswersPage, totalAnswerPages])

  // Refresh Answers handler
  const handleRefreshAnswers = async () => {
    await loadPublicAnswers()

    if (expandedConversationId) {
      await loadConversationMessages(expandedConversationId)
    }
  }

  return (
  <section className="mx-auto max-w-7xl px-4 pb-12 sm:px-6 lg:px-8">
    <div className="space-y-6">
      <div className="rounded-lg border border-border bg-card p-6">
        <div className="flex items-center gap-2 mb-6">
          <MessageSquare className="h-5 w-5 text-primary" />
          <h3 className="text-lg font-semibold text-foreground">Ask Questions!</h3>
          <span className="text-xs text-muted-foreground ml-auto">
            
          </span>
        </div>

        <p className="text-sm text-muted-foreground mb-4">
          Questions will appear anonymously in the Discussion Board section below.
        </p>

        {feedbackSent ? (
          <div className="flex items-center gap-3 rounded-lg border border-green-200 bg-green-50 p-4">
            <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0" />
            <div>
              <p className="font-medium text-green-900">Thank you for your entry!</p>
              <p className="text-sm text-green-700">We appreciate your input and will review it shortly.</p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium text-foreground block mb-2">
                Your Name (optional)
              </label>
              <input
                type="text"
                value={feedbackName}
                onChange={(e) => setFeedbackName(e.target.value)}
                placeholder="Enter your name or leave blank for anonymous"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-foreground block mb-2">
                Your Input
              </label>
              <textarea
                value={feedbackMessage}
                onChange={(e) => setFeedbackMessage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && e.ctrlKey && !sendingFeedback && feedbackMessage.trim()) {
                    handleSubmitFeedback()
                  }
                }}
                placeholder="Share your thoughts, suggestions, or report issues... (Ctrl+Enter to submit)"
                className="w-full rounded-md border border-input bg-background px-3 py-2.5 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 resize-vertical min-h-24"
              />
              <p className="text-xs text-muted-foreground mt-1.5">
                {feedbackMessage.length} characters • Ctrl+Enter to submit
              </p>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setFeedbackMessage("")
                  setFeedbackName("")
                }}
                disabled={sendingFeedback}
                className="px-4"
              >
                Clear
              </Button>
              <Button
                onClick={handleSubmitFeedback}
                disabled={sendingFeedback || !feedbackMessage.trim()}
                className="gap-2 px-4"
              >
                {sendingFeedback ? (
                  <>
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-background border-t-transparent" />
                    Sending...
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4" />
                    Send 
                  </>
                )}
              </Button>
            </div>
          </div>
        )}
      </div>

      <div className="rounded-lg border border-border bg-card p-6">
        <div className="flex items-center gap-2 mb-6">
          <CheckCircle2 className="h-5 w-5 text-primary" />
          <h3 className="text-lg font-semibold text-foreground">Discussion Board</h3>

          <Button
            variant="outline"
            size="sm"
            onClick={handleRefreshAnswers}
            disabled={loadingPublicAnswers}
            className="ml-auto gap-2 bg-transparent"
          >
            <RefreshCw className={`h-4 w-4 ${loadingPublicAnswers ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>

        {loadingPublicAnswers ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent mr-3" />
            Loading recent answers...
          </div>
        ) : publicAnswers.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border bg-muted/20 p-6 text-center">
            <MessageSquare className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
            <h4 className="font-semibold text-foreground">No public answers yet</h4>
            <p className="text-sm text-muted-foreground mt-1">
              Questions and other posts will appear here so everyone can see them.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {visiblePublicAnswers.map((item) => (
              <div
                key={item.id}
                className="rounded-lg border border-border bg-muted/20 p-4"
              >
                <div
                  id={
                    getThreadRootQuestionMessage(item.id)
                      ? getMessageElementId(getThreadRootQuestionMessage(item.id)!.id)
                      : undefined
                  }
                >
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1">
                    Question
                  </p>

                  <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span>{item.asked_by?.trim() ? item.asked_by : "Anonymous"}</span>
                    <span>•</span>
                    <span>
                      Asked on{" "}
                      {new Date(item.created_at).toLocaleDateString(undefined, {
                        year: "numeric",
                        month: "short",
                        day: "numeric",
                      })}
                    </span>
                  </div>

                  <p className="text-foreground font-medium">{item.question}</p>
                </div>

                {item.answer_text ? (
                  <>
                    <div
                      id={
                        getMainOfficialAnswerMessage(item.id)
                          ? getMessageElementId(getMainOfficialAnswerMessage(item.id)!.id)
                          : undefined
                      }
                      className="mt-4 rounded-md border border-primary/10 bg-primary/5 p-4"
                    >
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1">
                        Official Answer
                      </p>
                      <p className="text-sm text-foreground whitespace-pre-wrap">
                        {item.answer_text}
                      </p>
                    </div>

                    <div className="mt-3 text-xs text-muted-foreground">
                      Answered on {item.answered_at ? new Date(item.answered_at).toLocaleString() : "—"}
                    </div>
                  </>
                ) : getMainUserAnswerMessage(item.id) ? (
                  <>
                    <div
                      id={getMessageElementId(getMainUserAnswerMessage(item.id)!.id)}
                      className="mt-4 rounded-md border border-border bg-muted/30 p-4"
                    >
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1">
                        User Answer
                      </p>
                      <p className="text-sm text-foreground whitespace-pre-wrap">
                        {getMainUserAnswerMessage(item.id)!.message_text}
                      </p>
                    </div>

                    <div className="mt-3 text-xs text-muted-foreground">
                      Replied on {new Date(getMainUserAnswerMessage(item.id)!.created_at).toLocaleString()}
                    </div>
                  </>
                ) : null}

                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => toggleConversationThread(item.id)}
                  >
                    {expandedConversationId === item.id ? "Hide Thread" : "View Thread"}
                  </Button>

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => openReplyFormForQuestion(item.id)}
                  >
                    {replyConversationId === item.id &&
                    replyToMessageId === getThreadRootQuestionMessage(item.id)?.id
                      ? "Cancel Reply"
                      : "Reply to Question"}
                  </Button>
                </div>

                {replyConversationId === item.id &&
                  replyToMessageId === getThreadRootQuestionMessage(item.id)?.id &&
                  renderReplyForm(item.id, getThreadRootQuestionMessage(item.id)!.id)}

                {expandedConversationId === item.id && (
                  <div className="mt-4 rounded-lg border border-border bg-background p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-3">
                      Conversation Thread
                    </p>

                    {loadingConversationId === item.id ? (
                      <div className="flex items-center text-sm text-muted-foreground">
                        <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent mr-2" />
                        Loading thread...
                      </div>
                    ) : (
                      <div className="space-y-4">
                        {getTopLevelThreadMessages(item.id).length === 0 &&
                        getOrphanPublicReplies(item.id).length === 0 ? (
                          <p className="text-sm text-muted-foreground">
                            No additional follow-ups yet.
                          </p>
                        ) : (
                          <>
                            {getTopLevelThreadMessages(item.id).map((message) =>
                              renderConversationNode(item.id, message),
                            )}

                            {getOrphanPublicReplies(item.id).length > 0 && (
                              <div className="space-y-2">
                                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                  Additional Replies
                                </p>

                                {getOrphanPublicReplies(item.id).map((reply) => (
                                  <div
                                    key={reply.id}
                                    id={getMessageElementId(reply.id)}
                                    className="rounded-md border border-primary/20 bg-primary/5 p-3"
                                  >
                                    <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                                      <span>
                                        Official Reply • {new Date(reply.created_at).toLocaleString()}
                                      </span>

                                      {reply.reply_to_message_id && (
                                        <button
                                          type="button"
                                          onClick={() => scrollToMessage(reply.reply_to_message_id)}
                                          className="italic underline underline-offset-2 hover:text-foreground"
                                        >
                                          Re: {getReplyPreviewText(item.id, reply.reply_to_message_id)}
                                        </button>
                                      )}
                                    </div>

                                    <p className="text-sm text-foreground whitespace-pre-wrap">
                                      {reply.message_text}
                                    </p>

                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => openReplyFormForMessage(item.id, reply.id)}
                                      className="mt-2 h-auto p-0 text-xs font-bold text-muted-foreground hover:bg-transparent hover:text-foreground"
                                    >
                                      Reply
                                    </Button>

                                    {renderReplyForm(item.id, reply.id)}
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )}


              </div>
            ))}

            {publicAnswers.length > ANSWERS_PER_PAGE && (
              <div className="flex flex-col gap-3 pt-2 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-muted-foreground">
                  Showing {startAnswerIndex + 1}-
                  {Math.min(endAnswerIndex, publicAnswers.length)} of {publicAnswers.length} answers
                </p>

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentAnswersPage(1)}
                    disabled={currentAnswersPage === 1}
                  >
                    First
                  </Button>

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentAnswersPage((prev) => Math.max(prev - 1, 1))}
                    disabled={currentAnswersPage === 1}
                  >
                    Previous
                  </Button>

                  {answerPageNumbers.map((pageNumber) => (
                    <Button
                      key={pageNumber}
                      variant={currentAnswersPage === pageNumber ? "default" : "outline"}
                      size="sm"
                      onClick={() => setCurrentAnswersPage(pageNumber)}
                      className="min-w-10"
                    >
                      {pageNumber}
                    </Button>
                  ))}

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setCurrentAnswersPage((prev) => Math.min(prev + 1, totalAnswerPages))
                    }
                    disabled={currentAnswersPage === totalAnswerPages}
                  >
                    Next
                  </Button>

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentAnswersPage(totalAnswerPages)}
                    disabled={currentAnswersPage === totalAnswerPages}
                  >
                    Last
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  </section>
  )
}
