import { useEffect, useState } from "react";
import { askQuestionStream, getDocuments } from "../api";
import SearchBox from "../components/SearchBox";
import AnswerCard from "../components/AnswerCard";
import SourceList from "../components/SourceList";
import ErrorMessage from "../components/ErrorMessage";
import ConversationHistory from "../components/ConversationHistory";

const EXAMPLES = [
  { question: "How many vacation days do full-time staff get?", followUp: "What about part-time staff?" },
  { question: "How much does the Plus plan cost?", followUp: "How much storage does it include?" },
  { question: "Does the desktop app work on Linux?", followUp: "What can Linux users use instead?" },
  { question: "How long must my password be?", followUp: "Do I have to change it regularly?" },
];

const HISTORY_SENT = 3;

const CHANGED_TOPIC_HINT =
  "This was read as a follow-up to your earlier questions. If you changed topic, click New conversation and ask again.";

export default function SearchPage() {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState([]);
  const [turns, setTurns] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [partial, setPartial] = useState("");

  useEffect(() => {
    getDocuments()
      .then((data) => setCategories(data.categories || []))
      .catch(() => {});
  }, []);

  async function ask(text) {
    const earlier = result ? [...turns, { question: asked, answer: result.answer }] : turns;

    setQuestion(text);
    setAsked(text);
    setTurns(earlier);
    setLoading(true);
    setError("");
    setResult(null);
    setPartial("");

    try {
      const data = await askQuestionStream(text, category, earlier.slice(-HISTORY_SENT), setPartial);
      setResult(data);
      setQuestion("");
    } catch (err) {
      const notFound = err.message.startsWith("No relevant documents");
      setError(notFound && earlier.length > 0 ? `${err.message} ${CHANGED_TOPIC_HINT}` : err.message);
    } finally {
      setLoading(false);
      setPartial("");
    }
  }

  function newConversation() {
    setTurns([]);
    setResult(null);
    setError("");
    setAsked("");
    setQuestion("");
  }

  const started = loading || error || result;
  const followUp = result && EXAMPLES.find((example) => example.question === asked)?.followUp;
  const placeholder = !started
    ? "Ask a question, e.g. How many vacation days do I get?"
    : followUp
      ? `Ask a follow-up, e.g. ${followUp}`
      : "Ask a follow-up question";

  return (
    <div className={started ? "search-page" : "search-page intro"}>
      {!started && (
        <div className="hero">
          <p className="eyebrow">Brightpath knowledge base</p>
          <h1>What do you need to know?</h1>
          <p className="hero-text">
            Ask in plain words. Guidely reads the company documents and answers with the exact passages it used.
          </p>
        </div>
      )}

      <SearchBox
        question={question}
        category={category}
        categories={categories}
        loading={loading}
        placeholder={placeholder}
        onQuestion={setQuestion}
        onCategory={setCategory}
        onAsk={() => ask(question)}
      />

      {result && turns.length === 0 && (
        <p className="follow-up-hint">
          You can ask a follow-up question. Guidely remembers the last {HISTORY_SENT} questions.
        </p>
      )}

      {followUp && (
        <div className="examples follow-up">
          <span className="examples-label">Try a follow-up</span>
          <button className="chip" onClick={() => ask(followUp)}>
            {followUp}
          </button>
        </div>
      )}

      {!started && (
        <div className="examples">
          <span className="examples-label">Try asking</span>
          {EXAMPLES.map((example) => (
            <button key={example.question} className="chip" onClick={() => ask(example.question)}>
              {example.question}
            </button>
          ))}
        </div>
      )}

      {turns.length > 0 && <ConversationHistory turns={turns} onClear={newConversation} />}

      {started && <p className="current-question">{asked}</p>}

      {loading && partial && <AnswerCard answer={partial.replace(/\[\d*$/, "")} />}

      {loading && !partial && (
        <section className="answer-card">
          <div className="answer-label pulse">Reading the documents…</div>
          <div className="skeleton" />
          <div className="skeleton" />
          <div className="skeleton short" />
        </section>
      )}

      {error && <ErrorMessage message={error} />}

      {result && (
        <>
          <AnswerCard answer={result.answer} latencyMs={result.latency_ms} />
          <SourceList sources={result.sources} />
        </>
      )}
    </div>
  );
}
