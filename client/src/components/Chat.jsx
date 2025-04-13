import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { motion, AnimatePresence } from 'framer-motion';
import { format } from 'date-fns';
import apiClient from '../utils/api';
import './Chat.css';

// A simple function to generate a unique ID.
const generateUniqueId = () => {
  return `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
};

// Function to get current time in EST
const getCurrentTimeInEST = () => {
  try {
    // Create a date object for the current time
    const now = new Date();
    
    // Format the date to EST timezone
    // This uses the browser's timezone conversion capabilities
    const options = { 
      timeZone: 'America/New_York',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    };
    
    // Format the date according to the options
    const estDate = new Intl.DateTimeFormat('en-US', options).format(now);
    
    // Convert the formatted string to a more readable format
    // The format will be MM/DD/YYYY, HH:MM:SS
    const [datePart, timePart] = estDate.split(', ');
    const [month, day, year] = datePart.split('/');
    
    // Return in the format YYYY-MM-DD HH:MM:SS EST
    return `${year}-${month}-${day} ${timePart} EST`;
  } catch (error) {
    console.error("Error formatting EST time:", error);
    // Fallback to a simpler approach if the Intl API fails
    const now = new Date();
    const estOffset = -5; // EST is UTC-5
    const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
    const est = new Date(utc + (3600000 * estOffset));
    
    return format(est, 'yyyy-MM-dd HH:mm:ss') + ' EST';
  }
};

const TypingIndicator = () => (
  <div className="typing-indicator">
    <span></span>
    <span></span>
    <span></span>
  </div>
);

// Component to display the conversation summary
const ConversationSummary = ({ summary }) => {
  if (!summary) return null;
  
  return (
    <div className="conversation-summary">
      <h3>Conversation Summary</h3>
      <div className="summary-content">
        <div className="summary-section">
          <h4>Sentiment</h4>
          <p className={`sentiment ${summary.sentiment}`}>{summary.sentiment}</p>
        </div>
        
        <div className="summary-section">
          <h4>Keywords</h4>
          <div className="keywords">
            {summary.keywords.map((keyword, index) => (
              <span key={index} className="keyword-tag">{keyword}</span>
            ))}
          </div>
        </div>
        
        <div className="summary-section">
          <h4>Summary</h4>
          <p>{summary.summary}</p>
        </div>
        
        <div className="summary-section">
          <h4>Recommended Department</h4>
          <p className="department">{summary.department}</p>
        </div>
        
        <div className="summary-section">
          <h4>Additional Insights</h4>
          <ul>
            <li><strong>Urgency:</strong> {summary.insights.urgency}</li>
            <li><strong>Upsell Opportunity:</strong> {summary.insights.upsell_opportunity ? 'Yes' : 'No'}</li>
            <li><strong>Customer Interest:</strong> {summary.insights.customer_interest}</li>
            {summary.insights.additional_notes && (
              <li><strong>Notes:</strong> {summary.insights.additional_notes}</li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
};

const Chat = () => {
  const [messages, setMessages] = useState([
    { 
      id: generateUniqueId(), 
      sender: 'bot', 
      text: 'Hello! How can I help you today?',
      timestamp: new Date()
    }
  ]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [toolCallInProgress, setToolCallInProgress] = useState(false);
  const [conversationHistory, setConversationHistory] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [summary, setSummary] = useState(null);
  const [showSummary, setShowSummary] = useState(false);
  const [summaryGenerated, setSummaryGenerated] = useState(false);
  const [inactivityTimer, setInactivityTimer] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, summary]);

  useEffect(() => {
    if (!loading && !toolCallInProgress && inputRef.current) {
      inputRef.current.focus();
    }
  }, [loading, toolCallInProgress]);

  // Reset inactivity timer on user activity
  useEffect(() => {
    const resetTimer = () => {
      if (inactivityTimer) {
        clearTimeout(inactivityTimer);
      }
      
      // Only set a new timer if a summary hasn't been generated yet
      if (!summaryGenerated) {
        // Set a new timer for 5 minutes of inactivity
        const timer = setTimeout(() => {
          generateSummary();
        }, 5 * 60 * 1000); // 5 minutes
        
        setInactivityTimer(timer);
      }
    };
    
    // Add event listeners for user activity
    window.addEventListener('mousemove', resetTimer);
    window.addEventListener('keydown', resetTimer);
    window.addEventListener('click', resetTimer);
    
    // Initial timer setup
    resetTimer();
    
    // Cleanup
    return () => {
      window.removeEventListener('mousemove', resetTimer);
      window.removeEventListener('keydown', resetTimer);
      window.removeEventListener('click', resetTimer);
      if (inactivityTimer) {
        clearTimeout(inactivityTimer);
      }
    };
  }, [inactivityTimer, summaryGenerated]);

  // Function to generate a summary
  const generateSummary = async () => {
    // Don't generate if too short, already exists, or has already been generated
    if (conversationHistory.length < 2 || summary || summaryGenerated) return;
    
    try {
      setLoading(true);
      
      const response = await apiClient.post('/generate-summary', {
        conversation_history: conversationHistory,
        conversation_id: conversationId
      });
      
      const { summary: newSummary } = response.data;
      
      // Update the conversation ID if it was generated
      if (newSummary.conversation_id) {
        setConversationId(newSummary.conversation_id);
      }
      
      setSummary(newSummary);
      setShowSummary(true);
      setSummaryGenerated(true); // Mark that a summary has been generated
      
      // Clear the inactivity timer since we've generated a summary
      if (inactivityTimer) {
        clearTimeout(inactivityTimer);
        setInactivityTimer(null);
      }
    } catch (error) {
      console.error("Error generating summary:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!inputText.trim()) return;

    const userMessage = { 
      id: generateUniqueId(), 
      sender: 'user', 
      text: inputText,
      timestamp: new Date()
    };
    setMessages(prev => [...prev, userMessage]);

    const userInput = inputText;
    setInputText('');
    setLoading(true);

    try {
      // Use the stored conversation history if available, otherwise create a new one
      let formattedHistory = conversationHistory.length > 0 
        ? [...conversationHistory] 
        : [];
      
      // Get current time in EST
      const currentTime = getCurrentTimeInEST();
      
      // Add the current time context message
      formattedHistory.push({
        role: "system",
        content: `Current time: ${currentTime}`
      });
      
      // Add the current message to the history
      formattedHistory.push({
        role: 'user',
        content: userInput
      });

      const payload = {
        message: userInput,
        conversation_history: formattedHistory
      };

      const response = await apiClient.post('/chat', payload);
      const { chat_response, conversation_history: updatedHistory, tool_call_detected } = response.data;
      
      // Store the updated conversation history
      setConversationHistory(updatedHistory);

      // Check if a tool call was detected
      if (tool_call_detected) {
        // Set tool call in progress state
        setToolCallInProgress(true);
        
        // Add a message indicating that we're searching inventory
        const searchingMessage = { 
          id: generateUniqueId(), 
          sender: 'bot', 
          text: 'Please wait while I search our inventory.',
          timestamp: new Date()
        };
        setMessages(prev => [...prev, searchingMessage]);
        
        // Wait for the tool call to complete
        const toolCallResponse = await apiClient.post('/tool-call-result', {
          conversation_history: updatedHistory
        });
        
        // Get the final response after the tool call
        const { final_response, final_conversation_history } = toolCallResponse.data;
        
        // Update the conversation history
        setConversationHistory(final_conversation_history);
        
        // Add the final response as a message
        const finalMessage = { 
          id: generateUniqueId(), 
          sender: 'bot', 
          text: final_response,
          timestamp: new Date()
        };
        setMessages(prev => [...prev, finalMessage]);
        
        // Reset the tool call in progress state
        setToolCallInProgress(false);
      } else {
        // No tool call, just add the response as a message
        const botMessage = { 
          id: generateUniqueId(), 
          sender: 'bot', 
          text: chat_response,
          timestamp: new Date()
        };
        setMessages(prev => [...prev, botMessage]);
      }
      
      // Check if the user's message indicates the end of the conversation
      const endPhrases = ['goodbye', 'bye', 'thank you', 'thanks', 'end chat', 'end conversation'];
      const isEnding = endPhrases.some(phrase => 
        userInput.toLowerCase().includes(phrase)
      );
      
      if (isEnding && !summaryGenerated) {
        // Generate a summary when the conversation appears to be ending
        // Only if a summary hasn't been generated yet
        generateSummary();
      }
    } catch (error) {
      console.error("Error sending message:", error);
      const errorMessage = { 
        id: generateUniqueId(), 
        sender: 'bot', 
        text: 'Sorry, something went wrong. Please try again later.',
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errorMessage]);
      setToolCallInProgress(false);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h2>Nissan of Hendersonville Chat</h2>
      </div>
      <div className="chat-messages">
        <AnimatePresence>
          {messages.map(msg => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
              className={`chat-message ${msg.sender === 'user' ? 'user' : 'bot'}`}
            >
              <div className="message-content">
                <ReactMarkdown>{msg.text}</ReactMarkdown>
              </div>
              <div className="message-timestamp">
                {format(msg.timestamp, 'h:mm a')}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        {(loading || toolCallInProgress) && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="chat-message bot"
          >
            <TypingIndicator />
          </motion.div>
        )}
        <div ref={messagesEndRef} />
      </div>
      
      {showSummary && summary && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <ConversationSummary summary={summary} />
        </motion.div>
      )}
      
      <form className="chat-input-container" onSubmit={handleSend}>
        <input
          ref={inputRef}
          type="text"
          placeholder="Type your message here..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          disabled={loading || toolCallInProgress}
          className="chat-input"
        />
        <button 
          type="submit" 
          disabled={loading || toolCallInProgress || !inputText.trim()} 
          className={`chat-send-button ${(loading || toolCallInProgress) ? 'loading' : ''}`}
        >
          {loading ? 'Sending...' : toolCallInProgress ? 'Searching...' : 'Send'}
        </button>
      </form>
    </div>
  );
};

export default Chat;
