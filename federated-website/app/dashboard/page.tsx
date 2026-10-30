"use client"

import React from "react"

import { useState, useEffect, useRef } from "react"
import { PageLayout, StaggerContainer, StaggerItem } from "@/components/page-layout"
import {
  uploadFile,
  startTraining,
  checkHealth,
  testConnection,
  listUploadedFiles,
  deleteUploadedFile,
  submitFeedback,
  getPublicAnswers,
  getFeedbackMessages,
  createFeedbackFollowUp,
  type HealthResponse,
  type TrainingResult,
  type ProgressUpdate,
  type PublicAnswerItem,
  type ConversationMessageItem,
} from "@/lib/api"
import { SectionHeader } from "@/components/section-header"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Upload,
  Play,
  Wind,
  TrendingUp,
  Clock,
  FileText,
  AlertCircle,
  CheckCircle2,
  BarChart3,
  Shield,
  Server,
  Layers,
  Trash2,
  RefreshCw,
  MessageSquare,
  Send,
} from "lucide-react"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
} from "recharts"

// Mock data for wind speed demonstration (removed power data)
const mockForecastData = [
  { hour: "00:00", actual: 8.2, predicted: 8.0 },
  { hour: "02:00", actual: 9.1, predicted: 8.8 },
  { hour: "04:00", actual: 7.8, predicted: 8.1 },
  { hour: "06:00", actual: 10.5, predicted: 10.2 },
  { hour: "08:00", actual: 12.3, predicted: 11.9 },
  { hour: "10:00", actual: 11.8, predicted: 12.1 },
  { hour: "12:00", actual: 13.5, predicted: 13.2 },
  { hour: "14:00", actual: 14.2, predicted: 14.5 },
  { hour: "16:00", actual: 12.8, predicted: 13.0 },
  { hour: "18:00", actual: 10.5, predicted: 10.8 },
  { hour: "20:00", actual: 9.2, predicted: 9.0 },
  { hour: "22:00", actual: 8.5, predicted: 8.7 },
]

export default function DashboardPage() {
  // Form state
  const [files, setFiles] = useState<File[]>([])
  const [predictionLength, setPredictionLength] = useState("1")
  const [trainingModel, setTrainingModel] = useState("GPT4TS_LINEAR")
  const [federalAlgorithm, setFederalAlgorithm] = useState("FedAvg")
  const [numClients, setNumClients] = useState("5")
  const [numRounds, setNumRounds] = useState("5")
  const [localEpochs, setLocalEpochs] = useState("1")
  const [llmLayers, setLlmLayers] = useState("4")
  const [dropoutRate, setDropoutRate] = useState("0.2")
  const [mode, setMode] = useState("federated")
  const [horizon, setHorizon] = useState("1") // Declared horizon state

  // Centralized advanced params
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [learningRate, setLearningRate] = useState("0.0001329291894316216")
  const [batchSize, setBatchSize] = useState("64")
  const [seqLen, setSeqLen] = useState("336")
  const [epochs, setEpochs] = useState("20")
  const [weightDecay, setWeightDecay] = useState("0.0004335281794951569")
  const [warmupRounds, setWarmupRounds] = useState("3")
  const [patchSize, setPatchSize] = useState("16")
  const [patchStride, setPatchStride] = useState("16")
  const [hiddenSize, setHiddenSize] = useState("80")
  const [kernelSize, setKernelSize] = useState("7")
  const [centLlmLayers, setCentLlmLayers] = useState("2")
  const [proximalMu, setProximalMu] = useState("")

  // Federated advanced toggle
  const [showFedAdvanced, setShowFedAdvanced] = useState(false)

  const [showCentralAdvancedInfo, setShowCentralAdvancedInfo] = useState(true)
  const [showFedAdvancedInfo, setShowFedAdvancedInfo] = useState(true)

  // Optimized defaults per prediction length (centralized)
  const CENT_DEFAULTS: Record<string, Record<string, string>> = {
    "1":   { lr: "0.0001329291894316216", llm_layers: "2", epochs: "20", local_epochs: "5", weight_decay: "0.0004335281794951569", batch_size: "64", dropout: "0.2", warmup_rounds: "3", patch_size: "16", patch_stride: "16", hidden_size: "80", kernel_size: "7" },
    "72":  { lr: "0.0001329291894316216", llm_layers: "2", epochs: "20", local_epochs: "5", weight_decay: "0.0004335281794951569", batch_size: "64", dropout: "0.2", warmup_rounds: "3", patch_size: "16", patch_stride: "16", hidden_size: "80", kernel_size: "7" },
    "432": { lr: "0.0001329291894316216", llm_layers: "2", epochs: "20", local_epochs: "5", weight_decay: "0.0004335281794951569", batch_size: "64", dropout: "0.2", warmup_rounds: "3", patch_size: "16", patch_stride: "16", hidden_size: "80", kernel_size: "7" },
  }

  // Optimized defaults per prediction length (federated)
  const FED_DEFAULTS: Record<string, Record<string, string>> = {
    "1":   { lr: "0.0028292192255361887", llm_layers: "2", rounds: "19", local_epochs: "5", weight_decay: "0.021858816162324185", batch_size: "64", dropout: "0.30000000000000004", warmup_rounds: "0", patch_size: "32", patch_stride: "16", hidden_size: "48", kernel_size: "7", strategy: "FedAvg", proximal_mu: "" },
    "72":  { lr: "1.2199668475623259e-05", llm_layers: "2", rounds: "19", local_epochs: "2", weight_decay: "0.0034831202446644234", batch_size: "64", dropout: "0.5",                   warmup_rounds: "1", patch_size: "16", patch_stride: "8",  hidden_size: "24", kernel_size: "5", strategy: "FedAvg", proximal_mu: "" },
    "432": { lr: "3.0455368715396772e-05", llm_layers: "2", rounds: "10", local_epochs: "1", weight_decay: "0.00048284249748183273", batch_size: "32", dropout: "0.25",                  warmup_rounds: "4", patch_size: "32", patch_stride: "16", hidden_size: "40", kernel_size: "3", strategy: "FedProx", proximal_mu: "0.0014270403521460836" },
  }

  const applyPredLenDefaults = (predLen: string, currentMode: string) => {
    if (currentMode === "centralized") {
      const d = CENT_DEFAULTS[predLen]
      if (!d) return
      setLearningRate(d.lr)
      setCentLlmLayers(d.llm_layers)
      setEpochs(d.epochs)
      setLocalEpochs(d.local_epochs)
      setWeightDecay(d.weight_decay)
      setBatchSize(d.batch_size)
      setDropoutRate(d.dropout)
      setWarmupRounds(d.warmup_rounds)
      setPatchSize(d.patch_size)
      setPatchStride(d.patch_stride)
      setHiddenSize(d.hidden_size)
      setKernelSize(d.kernel_size)
    } else {
      const d = FED_DEFAULTS[predLen]
      if (!d) return
      setLearningRate(d.lr)
      setLlmLayers(d.llm_layers)
      setNumRounds(d.rounds)
      setLocalEpochs(d.local_epochs)
      setWeightDecay(d.weight_decay)
      setBatchSize(d.batch_size)
      setDropoutRate(d.dropout)
      setWarmupRounds(d.warmup_rounds)
      setPatchSize(d.patch_size)
      setPatchStride(d.patch_stride)
      setHiddenSize(d.hidden_size)
      setKernelSize(d.kernel_size)
      setFederalAlgorithm(d.strategy)
      setProximalMu(d.proximal_mu)
    }
  }

  const handlePredLenChange = (val: string) => {
    setPredictionLength(val)
    setHorizon(val)
    setShowCentralAdvancedInfo(true)
    setShowFedAdvancedInfo(true)
    applyPredLenDefaults(val, mode)
  }

  const handleModeChange = (val: string) => {
    setMode(val)
    applyPredLenDefaults(predictionLength, val)
  }

  // Processing state
  const [isProcessing, setIsProcessing] = useState(false)
  const [processingStep, setProcessingStep] = useState("")
  const [showResults, setShowResults] = useState(false)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (isProcessing) {
      setElapsedSeconds(0)
      timerRef.current = setInterval(() => setElapsedSeconds(s => s + 1), 1000)
    } else {
      if (timerRef.current) clearInterval(timerRef.current)
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [isProcessing])

  // API state
  const [apiConnected, setApiConnected] = useState<boolean | null>(null)
  const [apiHealth, setApiHealth] = useState<HealthResponse | null>(null)
  const [trainingResult, setTrainingResult] = useState<TrainingResult | null>(null)
  const [liveForecast, setLiveForecast] = useState<{step: number, predicted: number, actual: number | null}[]>([])
  const [liveRound, setLiveRound] = useState<{current: number, total: number} | null>(null)
  const [error, setError] = useState<string | null>(null)
  
  // File management state
  const [uploadedFiles, setUploadedFiles] = useState<Array<{filename: string, size: number, modified: string}>>([])
  const [loadingFiles, setLoadingFiles] = useState(false)
  const [deletingFile, setDeletingFile] = useState<string | null>(null)

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

  // Load uploaded files list
  const loadUploadedFiles = async () => {
    console.log("[v0] loadUploadedFiles called, apiConnected:", apiConnected)
    if (!apiConnected) {
      console.log("[v0] API not connected, skipping file load")
      return
    }
    setLoadingFiles(true)
    try {
      console.log("[v0] Fetching uploaded files from API...")
      const result = await listUploadedFiles()
      console.log("[v0] Files loaded:", result)
      setUploadedFiles(result.files)
    } catch (err) {
      console.error("[v0] Failed to load files:", err)
    } finally {
      setLoadingFiles(false)
    }
  }

  // Submit feedback
  const handleSubmitFeedback = async () => {
    if (!feedbackMessage.trim()) return
    
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
    if (!apiConnected) return

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

  // Delete a file
  const handleDeleteFile = async (filename: string) => {
    console.log("[v0] Delete requested for file:", filename)
    if (!confirm(`Are you sure you want to delete "${filename}"?`)) {
      console.log("[v0] Delete cancelled by user")
      return
    }
    
    setDeletingFile(filename)
    try {
      console.log("[v0] Calling deleteUploadedFile API...")
      const result = await deleteUploadedFile(filename)
      console.log("[v0] Delete result:", result)
      // Reload file list
      console.log("[v0] Reloading file list after delete...")
      await loadUploadedFiles()
    } catch (err) {
      console.error("[v0] Delete failed:", err)
      setError(err instanceof Error ? err.message : "Failed to delete file")
    } finally {
      setDeletingFile(null)
    }
  }

  // Check API connection on mount
  useEffect(() => {  
    const checkApiConnection = async () => {
      try {
        const connected = await testConnection()
        setApiConnected(connected)
        if (connected) {
          const health = await checkHealth()
          setApiHealth(health)
        }
      } catch {
        setApiConnected(false)
      }
    }
    checkApiConnection()
  }, [])

  useEffect(() => {
    if (apiConnected) {
      loadUploadedFiles()
      loadPublicAnswers()
    }
  }, [apiConnected])

  useEffect(() => {
    if (currentAnswersPage > totalAnswerPages) {
      setCurrentAnswersPage(totalAnswerPages)
    }
  }, [currentAnswersPage, totalAnswerPages])

  // File upload handler
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files)
      setFiles(prev => [...prev, ...newFiles])
      setError(null)
    }
  }

  // Refresh Answers handler
  const handleRefreshAnswers = async () => {
    await loadPublicAnswers()

    if (expandedConversationId) {
      await loadConversationMessages(expandedConversationId)
    }
  }

  // Remove a file from the selection
  const handleRemoveFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index))
  }

  // Training/upload handler - connects to FastAPI backend
  const handleStartTraining = async () => {
    setIsProcessing(true)
    setError(null)
    setTrainingResult(null)
    setLiveForecast([])
    setLiveRound(null)

    try {
      if (mode === "centralized") {
        // Centralized mode: Upload files -> then train on last one
        if (files.length === 0) {
          setError("Please select at least one CSV file to upload")
          return
        }

        // Step 1: Upload all files, keep track of saved filenames
        const savedFilenames: string[] = []
        for (let i = 0; i < files.length; i++) {
          const file = files[i]
          setProcessingStep(`Uploading file ${i + 1} of ${files.length}: ${file.name}...`)
          const uploadResult = await uploadFile(file)
          savedFilenames.push(uploadResult.file.filename)
        }

        // Reload file list after uploads
        await loadUploadedFiles()

        // Step 2: Train on the last uploaded file with config from the form
        const trainFilename = savedFilenames[savedFilenames.length - 1]
        setProcessingStep(
          `Training ${trainingModel} model (${predictionLength}-step horizon)...`
        )

        const config = {
          training_model: trainingModel,
          prediction_length: parseInt(predictionLength),
          dropout_rate: parseFloat(dropoutRate),
          mode: "centralized" as const,
          federated_algorithm: federalAlgorithm,
          num_clients: parseInt(numClients),
          num_rounds: parseInt(numRounds),
          local_epochs: parseInt(localEpochs),
          llm_layers: parseInt(centLlmLayers),
          learning_rate: parseFloat(learningRate),
          batch_size: parseInt(batchSize),
          seq_len: parseInt(seqLen),
          epochs: parseInt(epochs),
          weight_decay: parseFloat(weightDecay),
          warmup_rounds: parseInt(warmupRounds),
          patch_size: parseInt(patchSize),
          patch_stride: parseInt(patchStride),
          hidden_size: parseInt(hiddenSize),
          kernel_size: parseInt(kernelSize),
        }

        const onProgress = (p: ProgressUpdate) => {
          setLiveForecast(p.forecast)
          setLiveRound({ current: p.round, total: p.total_rounds })
          setShowResults(true)
        }
        const result = await startTraining(trainFilename, config, onProgress)
        setTrainingResult(result)
        setLiveForecast([])
        setShowResults(true)

        // Reset file selection
        setFiles([])
        const fileInput = document.getElementById("file-upload") as HTMLInputElement
        if (fileInput) fileInput.value = ""
      } else {
        // Federated mode: upload CSV → server runs real flwr simulation → results returned
        if (files.length === 0) {
          setError("Please select at least one CSV file to upload")
          return
        }

        // Step 1: Upload file
        const savedFilenames: string[] = []
        for (let i = 0; i < files.length; i++) {
          const file = files[i]
          setProcessingStep(`Uploading file ${i + 1} of ${files.length}: ${file.name}...`)
          const uploadResult = await uploadFile(file)
          savedFilenames.push(uploadResult.file.filename)
        }

        await loadUploadedFiles()

        // Step 2: Run real federated simulation via flwr on the server
        const trainFilename = savedFilenames[savedFilenames.length - 1]
        setProcessingStep(
          `Running federated simulation: ${trainingModel} / ${federalAlgorithm} / ${numClients} clients...`
        )

        const config = {
          training_model: trainingModel,
          prediction_length: parseInt(predictionLength),
          dropout_rate: parseFloat(dropoutRate),
          mode: "federated" as const,
          federated_algorithm: federalAlgorithm,
          num_clients: parseInt(numClients),
          num_rounds: parseInt(numRounds),
          local_epochs: parseInt(localEpochs),
          llm_layers: parseInt(llmLayers),
          learning_rate: parseFloat(learningRate),
          batch_size: parseInt(batchSize),
          weight_decay: parseFloat(weightDecay),
          warmup_rounds: parseInt(warmupRounds),
          patch_size: parseInt(patchSize),
          patch_stride: parseInt(patchStride),
          hidden_size: parseInt(hiddenSize),
          kernel_size: parseInt(kernelSize),
          ...(federalAlgorithm === "FedProx" && proximalMu ? { proximal_mu: parseFloat(proximalMu) } : {}),
        }

        const onProgress = (p: ProgressUpdate) => {
          setLiveForecast(p.forecast)
          setLiveRound({ current: p.round, total: p.total_rounds })
          setShowResults(true)
        }
        const result = await startTraining(trainFilename, config, onProgress)
        setTrainingResult(result)
        setLiveForecast([])
        setShowResults(true)

        setFiles([])
        const fileInput = document.getElementById("file-upload") as HTMLInputElement
        if (fileInput) fileInput.value = ""
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred")
    } finally {
      setIsProcessing(false)
      setProcessingStep("")
    }
  }

  return (
    <PageLayout>
      {/* Header */}
      <section className="bg-gradient-to-b from-primary/5 to-background">
        <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <SectionHeader
              badge="Interactive Demo"
              title="Wind Speed Forecasting Dashboard"
              description="Upload your wind data, configure training parameters, and view forecasting results. Choose between centralized or privacy-preserving federated learning."
              centered
            />
          </div>
        </div>
      </section>

      {/* API Connection Status */}
      <section className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div
          className={`rounded-lg border p-4 flex items-start gap-3 ${
            apiConnected === null
              ? "border-border bg-muted/30"
              : apiConnected
                ? "border-green-200 bg-green-50"
                : "border-amber-200 bg-amber-50"
          }`}
        >
          {apiConnected === null ? (
            <>
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent shrink-0 mt-0.5" />
              <div>
                <h4 className="font-semibold text-foreground">Checking API Connection...</h4>
                <p className="text-sm text-muted-foreground">
                  Attempting to connect to server
                </p>
              </div>
            </>
          ) : apiConnected ? (
            <>
              <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0 mt-0.5" />
              <div>
                <h4 className="font-semibold text-green-800">API Connected</h4>
                <p className="text-sm text-green-700">
                  Backend is running (v{apiHealth?.version || "unknown"}). Model service:{" "}
                  {apiHealth?.services.model || "unknown"}
                </p>
              </div>
            </>
          ) : (
            <>
              <AlertCircle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <h4 className="font-semibold text-amber-800">Demo Mode - API Not Connected</h4>
                <p className="text-sm text-amber-700">
                  FastAPI backend not detected. Start the backend with:{" "}
                  <code className="bg-amber-100 px-1 rounded">uvicorn main:app --reload</code>
                </p>
              </div>
            </>
          )}
        </div>
      </section>

      {/* Error Display */}
      {error && (
        <section className="mx-auto max-w-7xl px-4 pt-4 sm:px-6 lg:px-8">
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-red-600 shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-red-800">Error</h4>
              <p className="text-sm text-red-700">{error}</p>
            </div>
          </div>
        </section>
      )}

      {/* Training Success banner */}
{trainingResult && (
  <section className="mx-auto max-w-7xl px-4 pt-4 sm:px-6 lg:px-8">
    <div className="rounded-lg border border-green-200 bg-green-50 p-4 flex items-start gap-3">
      <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0 mt-0.5" />
      <div>
        <h4 className="font-semibold text-green-800">Training Complete</h4>
        <p className="text-sm text-green-700">
          {trainingResult.message} | MAE: {trainingResult.metrics.mae} m/s |{" "}
          RMSE: {trainingResult.metrics.rmse} m/s |{" "}
          Time: {trainingResult.training_time_seconds}s
        </p>
      </div>
    </div>
  </section>
)}



      {/* Training Progress (shown during processing) */}
      {isProcessing && (
        <section className="mx-auto max-w-7xl px-4 pt-4 sm:px-6 lg:px-8">
          <Card className="border-primary/20 bg-primary/5">
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className="h-10 w-10 animate-spin rounded-full border-4 border-primary border-t-transparent" />
                <div className="flex-1">
                  <h4 className="font-semibold text-foreground">
                    {mode === "federated" ? "Federated Training in Progress..." : "Centralized Training in Progress..."}
                  </h4>
                  <p className="text-sm text-muted-foreground">{processingStep}</p>
                </div>
                <div className="flex items-center gap-1.5 rounded-md bg-primary/10 px-3 py-1.5 text-primary">
                  <Clock className="h-4 w-4" />
                  <span className="font-mono text-sm font-semibold tabular-nums">
                    {String(Math.floor(elapsedSeconds / 60)).padStart(2, "0")}:{String(elapsedSeconds % 60).padStart(2, "0")}
                  </span>
                </div>
              </div>
              <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-muted">
                <div className="h-full w-2/3 animate-pulse rounded-full bg-primary" />
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                {mode === "federated"
                  ? "Your data stays on your device. Only model updates are shared with the server."
                  : "Your data is being processed on the server for model training."}
              </p>
            </CardContent>
          </Card>
        </section>
      )}

      {/* File Manager Section - Moved higher for better visibility */}
      {apiConnected && (
        <section className="mx-auto max-w-7xl px-4 pt-4 sm:px-6 lg:px-8">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <FileText className="h-5 w-5 text-primary" />
                    Uploaded Files
                  </CardTitle>
                  <CardDescription>
                    Manage your uploaded wind data files (used in centralized training)
                  </CardDescription>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={loadUploadedFiles}
                  disabled={loadingFiles}
                  className="gap-2 bg-transparent"
                >
                  <RefreshCw className={`h-4 w-4 ${loadingFiles ? "animate-spin" : ""}`} />
                  Refresh
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {loadingFiles ? (
                <div className="flex items-center justify-center py-8 text-muted-foreground">
                  <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent mr-3" />
                  Loading files...
                </div>
              ) : uploadedFiles.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <FileText className="h-12 w-12 text-muted-foreground mb-3" />
                  <h4 className="font-semibold text-foreground">No Files Uploaded</h4>
                  <p className="text-sm text-muted-foreground mt-1">
                    Upload CSV files using the form below to get started.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {uploadedFiles.map((file) => (
                    <div
                      key={file.filename}
                      className="flex items-center justify-between rounded-lg border border-border bg-muted/20 p-3 hover:bg-muted/40 transition-colors"
                    >
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        <FileText className="h-5 w-5 text-primary shrink-0" />
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-foreground truncate">{file.filename}</p>
                          <p className="text-xs text-muted-foreground">
                            {(file.size / 1024).toFixed(2)} KB • Uploaded{" "}
                            {new Date(file.modified).toLocaleString()}
                          </p>
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteFile(file.filename)}
                        disabled={deletingFile === file.filename}
                        className="text-destructive hover:text-destructive hover:bg-destructive/10 gap-2 shrink-0"
                      >
                        {deletingFile === file.filename ? (
                          <>
                            <div className="h-4 w-4 animate-spin rounded-full border-2 border-destructive border-t-transparent" />
                            Deleting...
                          </>
                        ) : (
                          <>
                            <Trash2 className="h-4 w-4" />
                            Delete
                          </>
                        )}
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      )}

      {/* Main Dashboard */}
      <section className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <StaggerContainer className="grid gap-6 xl:grid-cols-3">
          {/* Controls Panel */}
          <StaggerItem className="xl:col-span-1">
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-primary" />
                  Configuration
                </CardTitle>
                <CardDescription>Set up your training parameters</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* File Upload */}
                <div className="space-y-2">
                  <Label htmlFor="file-upload">Upload CSV Data</Label>
                  <div className="relative">
                    <input
                      id="file-upload"
                      type="file"
                      accept=".csv"
                      multiple
                      onChange={handleFileChange}
                      className="hidden"
                    />
                    <label
                      htmlFor="file-upload"
                      className="flex h-32 w-full cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-border bg-muted/30 transition-colors hover:border-primary hover:bg-muted/50"
                    >
                      <Upload className="h-8 w-8 text-muted-foreground mb-2" />
                      <span className="text-sm text-muted-foreground">
                        Click to upload CSV
                      </span>
                      <span className="text-xs text-muted-foreground mt-1">or drag and drop</span>
                    </label>
                  </div>

                  {/* File Preview Cards - Shows all selected files */}
                  {files.length > 0 && (
                    <div className="space-y-2">
                      {files.map((file, index) => (
                        <div
                          key={`${file.name}-${index}`}
                          className="rounded-lg border border-accent bg-accent/5 p-4 space-y-2 animate-in fade-in slide-in-from-top-2"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex items-start gap-3 flex-1 min-w-0">
                              <CheckCircle2 className="h-5 w-5 text-accent shrink-0 mt-0.5" />
                              <div className="flex-1 min-w-0">
                                <p className="font-semibold text-foreground text-sm truncate">{file.name}</p>
                                <p className="text-xs text-muted-foreground mt-1">
                                  {(file.size / 1024).toFixed(2)} KB
                                </p>
                              </div>
                            </div>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleRemoveFile(index)}
                              className="text-destructive hover:text-destructive hover:bg-destructive/10 shrink-0"
                            >
                              <Trash2 className="h-4 w-4" />
                              <span className="sr-only">Delete file</span>
                            </Button>
                          </div>
                        </div>
                      ))}
                      <p className="text-xs text-accent/80">
                        {files.length} file{files.length > 1 ? "s" : ""} ready to upload. Click "Start Forecasting" below to begin.
                      </p>
                    </div>
                  )}
                </div>

                {/* Training Model Selection */}
                <div className="space-y-2">
                  <Label htmlFor="model">Training Model</Label>
                  <Select value={trainingModel} onValueChange={setTrainingModel}>
                    <SelectTrigger id="model">
                      <SelectValue placeholder="Select model" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="GPT4TS_LINEAR">GPT4TS</SelectItem>
                      <SelectItem value="LLAMA_LINEAR">LLaMA</SelectItem>
                      <SelectItem value="BERT_LINEAR">BERT</SelectItem>
                      <SelectItem value="BART_LINEAR">BART</SelectItem>
                      <SelectItem value="OPT_LINEAR">OPT</SelectItem>
                      <SelectItem value="GEMMA_LINEAR">Gemma</SelectItem>
                      <SelectItem value="QWEN_LINEAR">Qwen</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">Selected: {trainingModel.replace("_LINEAR", "")}</p>
                </div>

                {/* Prediction Length */}
                <div className="space-y-2">
                  <Label htmlFor="prediction-length">Prediction Length (Steps)</Label>
                  <Select value={predictionLength} onValueChange={handlePredLenChange}>
                    <SelectTrigger id="prediction-length">
                      <SelectValue placeholder="Select prediction length" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1">1</SelectItem>
                      <SelectItem value="72">72</SelectItem>
                      <SelectItem value="432">432</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">Forecast {predictionLength} hour{predictionLength !== "1" ? "s" : ""} ahead</p>
                </div>

                {/* Learning Rate - basic, centralized only */}
                {mode === "centralized" && (
                  <div className="space-y-2">
                    <Label htmlFor="lr-basic">Learning Rate</Label>
                    <input
                      id="lr-basic"
                      type="text"
                      inputMode="decimal"
                      value={learningRate}
                      onChange={(e) => setLearningRate(e.target.value)}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      placeholder="0.0001329291894316216"
                    />
                  </div>
                )}

                {/* Advanced toggle - centralized only */}
                {mode === "centralized" && (
                  <div className="pt-1">
                    <button
                      type="button"
                      onClick={() => setShowAdvanced((v) => !v)}
                      className="text-xs font-medium text-primary underline underline-offset-2 hover:no-underline"
                    >
                      {showAdvanced ? "▲ Hide Advanced Parameters" : "▼ Show Advanced Parameters"}
                    </button>
                    <p className="text-xs text-muted-foreground mt-1">
                      {showAdvanced ? "Editing optimized defaults for pred-len " + predictionLength : "Using optimized defaults for pred-len " + predictionLength}
                    </p>
                  </div>
                )}

                {/* Advanced params - centralized only */}
                {mode === "centralized" && showAdvanced && (
                  <div className="relative space-y-4 rounded-lg border border-border bg-muted/20 p-4">
                    {showCentralAdvancedInfo && (
                      <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800 2xl:absolute 2xl:left-[-14rem] 2xl:top-0 2xl:mb-0 2xl:w-44">
                        <button
                          type="button"
                          onClick={() => setShowCentralAdvancedInfo(false)}
                          className="absolute right-2 top-2 text-lg font-semibold leading-none text-blue-700 hover:text-blue-900"
                          aria-label="Close advanced info"
                        >
                          ×
                        </button>
                        <p className="pr-4 font-medium">Recommended defaults</p>
                        <p className="mt-1">
                          These advanced parameters are pre-filled with best-performing settings for prediction length {predictionLength}, based on prior experiments.
                        </p>
                      </div>
                    )}

                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Advanced Parameters
                    </p>

                    {/* Dropout Rate */}
                    <div className="space-y-1">
                      <Label htmlFor="dropout" className="text-xs">Dropout Rate</Label>
                      <input
                        id="dropout"
                        type="number"
                        min="0"
                        max="0.5"
                        step="0.05"
                        value={dropoutRate}
                        onChange={(e) => {
                          const val = parseFloat(e.target.value)
                          if (val >= 0 && val <= 0.5) setDropoutRate(e.target.value)
                        }}
                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        placeholder="0.2"
                      />
                    </div>

                    {/* LLM Layers */}
                    <div className="space-y-1">
                      <Label htmlFor="cent-llm-layers" className="text-xs">LLM Layers</Label>
                      <input
                        id="cent-llm-layers"
                        type="number"
                        min="1"
                        max="12"
                        value={centLlmLayers}
                        onChange={(e) => setCentLlmLayers(e.target.value)}
                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      />
                    </div>

                    {/* Epochs */}
                    <div className="space-y-1">
                      <Label htmlFor="epochs" className="text-xs">Epochs (Rounds)</Label>
                      <input
                        id="epochs"
                        type="number"
                        min="1"
                        max="100"
                        value={epochs}
                        onChange={(e) => setEpochs(e.target.value)}
                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      />
                    </div>

                    {/* Batch Size */}
                    <div className="space-y-1">
                      <Label htmlFor="batch-size" className="text-xs">Batch Size</Label>
                      <input
                        id="batch-size"
                        type="number"
                        min="1"
                        value={batchSize}
                        onChange={(e) => setBatchSize(e.target.value)}
                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      />
                    </div>

                    {/* Weight Decay */}
                    <div className="space-y-1">
                      <Label htmlFor="weight-decay" className="text-xs">Weight Decay</Label>
                      <input
                        id="weight-decay"
                        type="text"
                        inputMode="decimal"
                        value={weightDecay}
                        onChange={(e) => setWeightDecay(e.target.value)}
                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      />
                    </div>

                    {/* Warmup Rounds */}
                    <div className="space-y-1">
                      <Label htmlFor="warmup" className="text-xs">Warmup Rounds</Label>
                      <input
                        id="warmup"
                        type="number"
                        min="0"
                        value={warmupRounds}
                        onChange={(e) => setWarmupRounds(e.target.value)}
                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      />
                    </div>

                    {/* Patch Size / Stride */}
                    <div className="grid grid-cols-2 gap-2">
                      <div className="space-y-1">
                        <Label htmlFor="patch-size" className="text-xs">Patch Size</Label>
                        <input
                          id="patch-size"
                          type="number"
                          min="1"
                          value={patchSize}
                          onChange={(e) => setPatchSize(e.target.value)}
                          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="patch-stride" className="text-xs">Patch Stride</Label>
                        <input
                          id="patch-stride"
                          type="number"
                          min="1"
                          value={patchStride}
                          onChange={(e) => setPatchStride(e.target.value)}
                          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        />
                      </div>
                    </div>

                    {/* Hidden Size */}
                    <div className="space-y-1">
                      <Label htmlFor="hidden-size" className="text-xs">Hidden Size</Label>
                      <input
                        id="hidden-size"
                        type="number"
                        min="1"
                        value={hiddenSize}
                        onChange={(e) => setHiddenSize(e.target.value)}
                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      />
                    </div>

                    {/* Kernel Size */}
                    <div className="space-y-1">
                      <Label htmlFor="kernel-size" className="text-xs">Kernel Size</Label>
                      <input
                        id="kernel-size"
                        type="number"
                        min="1"
                        value={kernelSize}
                        onChange={(e) => setKernelSize(e.target.value)}
                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      />
                    </div>
                  </div>
                )}

                {/* Training Mode */}
                <div className="space-y-2">
                  <Label htmlFor="mode">Training Mode</Label>
                  <Select value={mode} onValueChange={handleModeChange}>
                    <SelectTrigger id="mode">
                      <SelectValue placeholder="Select mode" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="federated">
                        <div className="flex items-center gap-2">
                          <Shield className="h-4 w-4" />
                          Federated (Privacy-Preserving)
                        </div>
                      </SelectItem>
                      <SelectItem value="centralized">
                        <div className="flex items-center gap-2">
                          <Server className="h-4 w-4" />
                          Centralized (Server Upload)
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  <div
                    className={`text-xs p-2 rounded ${mode === "federated" ? "bg-green-50 text-green-700" : "bg-amber-50 text-amber-700"}`}
                  >
                    {mode === "federated"
                      ? "Data stays on your device. Only model updates are shared."
                      : "Data is uploaded to server for training."}
                  </div>
                </div>

                {/* Federated Algorithm Selection - Only for Federated Mode */}
                {mode === "federated" && (
                  <div className="space-y-2 pt-2 border-t border-border">
                    <Label htmlFor="algorithm">Federated Learning Algorithm</Label>
                    <Select value={federalAlgorithm} onValueChange={setFederalAlgorithm}>
                      <SelectTrigger id="algorithm">
                        <SelectValue placeholder="Select algorithm" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="FedAvg">FedAvg - Federated Averaging</SelectItem>
                        <SelectItem value="FedProx">FedProx - Proximal Term</SelectItem>
                        <SelectItem value="SCAFFOLD">SCAFFOLD - Control Variates</SelectItem>
                        <SelectItem value="StatAvg">StatAvg - Statistics Averaging</SelectItem>
                        <SelectItem value="FedPer">FedPer - Personalized Head</SelectItem>
                        <SelectItem value="FedLN">FedLN - Local Layer Norms</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">Selected: {federalAlgorithm}</p>
                  </div>
                )}

                {/* Federated basic + advanced */}
                {mode === "federated" && (
                  <>
                    {/* Learning Rate - basic */}
                    <div className="space-y-2">
                      <Label htmlFor="fed-lr">Learning Rate</Label>
                      <input
                        id="fed-lr"
                        type="text"
                        inputMode="decimal"
                        value={learningRate}
                        onChange={(e) => setLearningRate(e.target.value)}
                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      />
                    </div>

                    {/* Number of Clients */}
                    <div className="space-y-2">
                      <Label htmlFor="clients">Number of Clients</Label>
                      <div className="flex gap-2 items-center">
                        <input id="clients" type="number" min="1" max="10" value={numClients}
                          onChange={(e) => { const v = parseInt(e.target.value); if (v >= 1 && v <= 10) setNumClients(e.target.value) }}
                          className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm" placeholder="5" />
                        <span className="text-sm text-muted-foreground font-mono">/ 10</span>
                      </div>
                    </div>

                    {/* Advanced toggle */}
                    <div className="pt-1">
                      <button type="button" onClick={() => setShowFedAdvanced((v) => !v)}
                        className="text-xs font-medium text-primary underline underline-offset-2 hover:no-underline">
                        {showFedAdvanced ? "▲ Hide Advanced Parameters" : "▼ Show Advanced Parameters"}
                      </button>
                      <p className="text-xs text-muted-foreground mt-1">
                        {showFedAdvanced ? "Editing optimized defaults for pred-len " + predictionLength : "Using optimized defaults for pred-len " + predictionLength}
                      </p>
                    </div>

                    {/* Advanced panel */}
                    {showFedAdvanced && (
                      <div className="relative space-y-4 rounded-lg border border-border bg-muted/20 p-4">
                        {showFedAdvancedInfo && (
                          <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800 2xl:absolute 2xl:left-[-14rem] 2xl:top-0 2xl:mb-0 2xl:w-44">
                            <button
                              type="button"
                              onClick={() => setShowFedAdvancedInfo(false)}
                              className="absolute right-2 top-2 text-lg font-semibold leading-none text-blue-700 hover:text-blue-900"
                              aria-label="Close advanced info"
                            >
                              ×
                            </button>
                            <p className="pr-4 font-medium">Recommended defaults</p>
                            <p className="mt-1">
                              These advanced parameters are pre-filled with best-performing settings for prediction length {predictionLength}, based on prior experiments.
                            </p>
                          </div>
                        )}

                        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                          Advanced Parameters
                        </p>

                        {/* Dropout */}
                        <div className="space-y-1">
                          <Label htmlFor="fed-dropout" className="text-xs">Dropout Rate</Label>
                          <input
                            id="fed-dropout"
                            type="number"
                            min="0"
                            max="1"
                            step="0.05"
                            value={dropoutRate}
                            onChange={(e) => setDropoutRate(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                          />
                        </div>

                        {/* LLM Layers */}
                        <div className="space-y-1">
                          <Label htmlFor="fed-llm-layers" className="text-xs">LLM Layers</Label>
                          <input
                            id="fed-llm-layers"
                            type="number"
                            min="1"
                            max="12"
                            value={llmLayers}
                            onChange={(e) => setLlmLayers(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                          />
                        </div>

                        {/* Rounds */}
                        <div className="space-y-1">
                          <Label htmlFor="fed-rounds" className="text-xs">Communication Rounds</Label>
                          <input
                            id="fed-rounds"
                            type="number"
                            min="1"
                            max="50"
                            value={numRounds}
                            onChange={(e) => setNumRounds(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                          />
                        </div>

                        {/* Local Epochs */}
                        <div className="space-y-1">
                          <Label htmlFor="fed-local-epochs" className="text-xs">Local Epochs per Round</Label>
                          <input
                            id="fed-local-epochs"
                            type="number"
                            min="1"
                            max="20"
                            value={localEpochs}
                            onChange={(e) => setLocalEpochs(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                          />
                        </div>

                        {/* Batch Size */}
                        <div className="space-y-1">
                          <Label htmlFor="fed-batch" className="text-xs">Batch Size</Label>
                          <input
                            id="fed-batch"
                            type="number"
                            min="1"
                            value={batchSize}
                            onChange={(e) => setBatchSize(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                          />
                        </div>

                        {/* Weight Decay */}
                        <div className="space-y-1">
                          <Label htmlFor="fed-wd" className="text-xs">Weight Decay</Label>
                          <input
                            id="fed-wd"
                            type="text"
                            inputMode="decimal"
                            value={weightDecay}
                            onChange={(e) => setWeightDecay(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                          />
                        </div>

                        {/* Warmup Rounds */}
                        <div className="space-y-1">
                          <Label htmlFor="fed-warmup" className="text-xs">Warmup Rounds</Label>
                          <input
                            id="fed-warmup"
                            type="number"
                            min="0"
                            value={warmupRounds}
                            onChange={(e) => setWarmupRounds(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                          />
                        </div>

                        {/* Patch Size / Stride */}
                        <div className="grid grid-cols-2 gap-2">
                          <div className="space-y-1">
                            <Label htmlFor="fed-patch-size" className="text-xs">Patch Size</Label>
                            <input
                              id="fed-patch-size"
                              type="number"
                              min="1"
                              value={patchSize}
                              onChange={(e) => setPatchSize(e.target.value)}
                              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                            />
                          </div>
                          <div className="space-y-1">
                            <Label htmlFor="fed-patch-stride" className="text-xs">Patch Stride</Label>
                            <input
                              id="fed-patch-stride"
                              type="number"
                              min="1"
                              value={patchStride}
                              onChange={(e) => setPatchStride(e.target.value)}
                              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                            />
                          </div>
                        </div>

                        {/* Hidden Size */}
                        <div className="space-y-1">
                          <Label htmlFor="fed-hidden" className="text-xs">Hidden Size</Label>
                          <input
                            id="fed-hidden"
                            type="number"
                            min="1"
                            value={hiddenSize}
                            onChange={(e) => setHiddenSize(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                          />
                        </div>

                        {/* Kernel Size */}
                        <div className="space-y-1">
                          <Label htmlFor="fed-kernel" className="text-xs">Kernel Size</Label>
                          <input
                            id="fed-kernel"
                            type="number"
                            min="1"
                            value={kernelSize}
                            onChange={(e) => setKernelSize(e.target.value)}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                          />
                        </div>

                        {/* Proximal Mu (FedProx only) */}
                        {federalAlgorithm === "FedProx" && (
                          <div className="space-y-1">
                            <Label htmlFor="fed-mu" className="text-xs">Proximal Mu (FedProx)</Label>
                            <input
                              id="fed-mu"
                              type="text"
                              inputMode="decimal"
                              value={proximalMu}
                              onChange={(e) => setProximalMu(e.target.value)}
                              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                              placeholder="0.0014270403521460836"
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}

                {/* Start Button */}
                <Button
                  className="w-full gap-2"
                  onClick={handleStartTraining}
                  disabled={isProcessing || files.length === 0}
                >
                  {isProcessing ? (
                    <>
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent" />
                      Processing...
                    </>
                  ) : (
                    <>
                      <Play className="h-4 w-4" />
                      Start Forecasting
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>
          </StaggerItem>

          {/* Results Panel */}
          <StaggerItem className="xl:col-span-2">
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5 text-primary" />
                  Wind Speed Forecasting Results
                </CardTitle>
                <CardDescription>
                  {showResults && trainingResult
                    ? `${trainingResult.prediction_length}-step wind speed forecast using ${trainingResult.model_name} (${mode === "federated" ? "Federated" : "Centralized"})`
                    : showResults
                      ? `${predictionLength}-step forecast ${mode === "federated" ? "(Federated Model)" : "(Centralized Model)"}`
                      : "Configure and run to see predictions"}
                </CardDescription>
              </CardHeader>
              <CardContent>
                {showResults ? (
                  <div className="space-y-6">
                    {/* Stats Row - Only MAE + RMSE + Time */}
                    <div className="grid gap-4 sm:grid-cols-3">
                      <div className="rounded-lg border border-border bg-muted/30 p-4">
                        <div className="flex items-center gap-2 text-muted-foreground text-sm">
                          <Wind className="h-4 w-4" />
                          MAE
                        </div>
                        <div className="mt-1 text-2xl font-bold text-foreground">
                          {trainingResult ? trainingResult.metrics.mae : "--"}
                        </div>
                        <div className="text-xs text-muted-foreground">Mean Absolute Error (normalized)</div>
                      </div>
                      <div className="rounded-lg border border-border bg-muted/30 p-4">
                        <div className="flex items-center gap-2 text-muted-foreground text-sm">
                          <BarChart3 className="h-4 w-4" />
                          RMSE
                        </div>
                        <div className="mt-1 text-2xl font-bold text-foreground">
                          {trainingResult ? trainingResult.metrics.rmse : "--"}
                        </div>
                        <div className="text-xs text-muted-foreground">Root Mean Square Error (normalized)</div>
                      </div>
                      <div className="rounded-lg border border-border bg-muted/30 p-4">
                        <div className="flex items-center gap-2 text-muted-foreground text-sm">
                          <Clock className="h-4 w-4" />
                          Time
                        </div>
                        <div className="mt-1 text-2xl font-bold text-foreground">
                          {trainingResult ? `${trainingResult.training_time_seconds}s` : "--s"}
                        </div>
                        <div className="text-xs text-muted-foreground">Training Duration</div>
                      </div>
                    </div>

                    {/* Federated Mode Info Panel */}
                    {mode === "federated" && trainingResult && (
                      <div className="rounded-lg border border-green-200 bg-green-50 p-4">
                        <h4 className="font-semibold text-green-800 flex items-center gap-2 mb-3">
                          <Shield className="h-4 w-4 text-green-600" />
                          Federated Learning - Privacy Preserved
                        </h4>
                        <div className="grid gap-3 sm:grid-cols-3">
                          <div>
                            <div className="text-xs text-muted-foreground">Algorithm</div>
                            <div className="text-lg font-semibold text-foreground">
                              {federalAlgorithm}
                            </div>
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground">Clients</div>
                            <div className="text-lg font-semibold text-foreground">
                              {numClients}
                            </div>
                          </div>
                          <div>
                            <div className="text-xs text-muted-foreground">Model</div>
                            <div className="text-lg font-semibold text-foreground">
                              {trainingResult.model_name}
                            </div>
                          </div>
                        </div>
                        <p className="text-xs text-green-600 mt-3">
                          Data stayed on each client device. Only model updates were aggregated on the server.
                        </p>
                      </div>
                    )}

                    {/* Wind Speed Chart */}
                    <div>
                      <h4 className="font-semibold text-foreground mb-3 flex items-center gap-2">
                        <Wind className="h-4 w-4 text-primary" />
                        Wind Speed Forecast
                        {(trainingResult || liveForecast.length > 0) && (
                          <span className="text-xs font-normal text-muted-foreground ml-1">
                            {liveRound && isProcessing
                              ? `— Round ${liveRound.current}/${liveRound.total} (live)`
                              : trainingResult ? `— ${trainingResult.forecast.length} steps (normalized scale)` : ""}
                          </span>
                        )}
                      </h4>

                      <div style={{ width: "100%", height: 280 }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart
                            data={
                              trainingResult && !isProcessing
                                ? trainingResult.forecast.map((p) => ({
                                    label: `S${p.step}`,
                                    predicted: p.predicted,
                                    ...(p.actual !== null && p.actual !== undefined
                                      ? { actual: p.actual }
                                      : {}),
                                  }))
                                : liveForecast.length > 0
                                ? liveForecast.map((p) => ({
                                    label: `S${p.step}`,
                                    predicted: p.predicted,
                                    ...(p.actual !== null ? { actual: p.actual } : {}),
                                  }))
                                : mockForecastData.map((d) => ({
                                    label: d.hour,
                                    predicted: d.predicted,
                                    actual: d.actual,
                                  }))
                            }
                            margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                            <XAxis
                              dataKey="label"
                              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                              interval="preserveStartEnd"
                            />
                            <YAxis
                              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                              label={{
                                value: trainingResult && trainingResult.forecast.length > 0 ? "normalized" : "m/s",
                                angle: -90,
                                position: "insideLeft",
                                fontSize: 12,
                                fill: "hsl(var(--muted-foreground))",
                              }}
                              domain={["auto", "auto"]}
                            />
                            <Tooltip
                              contentStyle={{
                                backgroundColor: "hsl(var(--background))",
                                border: "1px solid hsl(var(--border))",
                                borderRadius: "6px",
                                fontSize: "12px",
                                color: "hsl(var(--foreground))",
                              }}
                              formatter={(value: number, name: string) => [
                                trainingResult && trainingResult.forecast.length > 0
                                  ? Number(value).toFixed(4)
                                  : `${Number(value).toFixed(2)} m/s`,
                                name,
                              ]}
                              labelFormatter={(label) => `${label}`}
                            />
                            <Legend wrapperStyle={{ fontSize: "12px" }} />
                            {((liveForecast.length > 0 && liveForecast.some(p => p.actual !== null)) ||
                              (trainingResult && trainingResult.forecast.some(
                                (p) => p.actual !== null && p.actual !== undefined,
                              )) ||
                              (!trainingResult && liveForecast.length === 0)) && (
                              <Line
                                type="monotone"
                                dataKey="actual"
                                stroke="#A23B72"
                                strokeWidth={2}
                                dot={false}
                                name="Actual"
                                connectNulls={false}
                                isAnimationActive={false}
                              />
                            )}
                            <Line
                              type="monotone"
                              dataKey="predicted"
                              stroke="#2E86AB"
                              strokeWidth={2}
                              strokeDasharray="5 5"
                              dot={false}
                              name="Predicted"
                              isAnimationActive={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    {/* Download Results */}
                    {trainingResult && (
                      trainingResult.download_training_summary ||
                      trainingResult.download_timing_summary
                    ) && (
                      <div className="rounded-lg border border-border bg-muted/20 p-4">
                        <h4 className="font-semibold text-foreground text-sm mb-3 flex items-center gap-2">
                          <FileText className="h-4 w-4 text-primary" />
                          Download Training Results
                        </h4>
                        <div className="flex flex-wrap gap-3">
                          {trainingResult?.download_training_summary && (
                            <a
                              href={`${process.env.NEXT_PUBLIC_TRAINING_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"}${trainingResult.download_training_summary}`}
                              download="training_summary.csv"
                              className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground shadow-sm hover:bg-muted/50 transition-colors"
                            >
                              {/* inline SVG so no extra import needed */}
                              <svg
                                xmlns="http://www.w3.org/2000/svg"
                                className="h-4 w-4 text-primary"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth={2}
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              >
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                                <polyline points="7 10 12 15 17 10" />
                                <line x1="12" y1="15" x2="12" y2="3" />
                              </svg>
                              training_summary.csv
                            </a>
                          )}
                          {trainingResult?.download_timing_summary && (
                            <a
                              href={`${process.env.NEXT_PUBLIC_TRAINING_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001"}${trainingResult.download_timing_summary}`}
                              download="timing_summary.csv"
                              className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground shadow-sm hover:bg-muted/50 transition-colors"
                            >
                              <svg
                                xmlns="http://www.w3.org/2000/svg"
                                className="h-4 w-4 text-primary"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth={2}
                                strokeLinecap="round"
                                strokeLinejoin="round"
                              >
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                                <polyline points="7 10 12 15 17 10" />
                                <line x1="12" y1="15" x2="12" y2="3" />
                              </svg>
                              timing_summary.csv
                            </a>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground mt-2">
                          Per-round metrics and wall-clock timing from this training run.
                        </p>
                      </div>
                    )}

                    {/* Training Info (if complete) */}
                    {trainingResult && (
                      <div className="rounded-lg border border-border bg-muted/20 p-4">
                        <h4 className="font-semibold text-foreground text-sm mb-2">Training Summary</h4>
                        <div className="grid gap-2 sm:grid-cols-4 text-sm">
                          <div>
                            <span className="text-muted-foreground">Model:</span>{" "}
                            <span className="text-foreground">{trainingResult.model_name}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Horizon:</span>{" "}
                            <span className="text-foreground">{trainingResult.prediction_length} steps</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Dropout:</span>{" "}
                            <span className="text-foreground">{trainingResult.dropout_rate}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Time:</span>{" "}
                            <span className="text-foreground">{trainingResult.training_time_seconds}s</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex h-[400px] flex-col items-center justify-center text-center">
                    <Clock className="h-12 w-12 text-muted-foreground mb-4" />
                    <h4 className="font-semibold text-foreground">No Results Yet</h4>
                    <p className="text-sm text-muted-foreground mt-1 max-w-xs">
                      Upload your data and click &quot;Start Forecasting&quot; to see wind speed predictions.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </StaggerItem>
        </StaggerContainer>
      </section>

      {/* Feedback + Recent Answers */}
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
                disabled={loadingPublicAnswers || !apiConnected}
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
    </PageLayout>
  )
}
