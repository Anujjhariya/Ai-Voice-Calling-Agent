import { useState } from 'react';
import './App.css';

function App() {
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [voice, setVoice] = useState('Polly.Aditi');
  const [status, setStatus] = useState('idle'); // idle, calling, success, error
  const [message, setMessage] = useState('Ready to make a call.');

  const handleMakeCall = async (e) => {
    e.preventDefault();
    if (!name || !phone) {
      setMessage('Please enter both name and phone number.');
      setStatus('error');
      return;
    }

    setStatus('calling');
    setMessage(`Dialing ${name} at ${phone}...`);

    try {
      // Connect to the Python FastAPI Server
      const response = await fetch('http://localhost:8000/ivr/trigger_campaign', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          voice: voice,
          leads: [
            { name: name, phone: phone }
          ]
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setStatus('success');
        setMessage('Campaign successfully queued! The server will dial them sequentially.');
      } else {
        setStatus('error');
        setMessage(`Error: ${data.detail || 'Failed to trigger call'}`);
      }
    } catch (error) {
      setStatus('error');
      setMessage(`Connection failed. Is the Python server running on port 8000?`);
    }
  };

  const handleTestCall = async (e) => {
    e.preventDefault();
    
    setStatus('calling');
    setMessage(`Generating premium audio for ${voice}...`);

    try {
      const audioUrl = `http://localhost:8000/ivr/preview_voice?voice=${voice}`;
      
      const audio = new Audio(audioUrl);
      
      audio.onplay = () => {
        setStatus('success');
        setMessage('Playing premium audio directly through your speakers!');
      };
      
      audio.onerror = () => {
        setStatus('error');
        setMessage('Failed to load premium audio from the server.');
      };

      await audio.play();
    } catch (error) {
      setStatus('error');
      setMessage(`Connection failed. Is the Python server running on port 8000?`);
    }
  };

  return (
    <div className="dashboard-container">
      <div className="header">
        <h1>Voice AI Dashboard</h1>
        <p>Trigger ultra-realistic AI calls instantly.</p>
      </div>

      <div className="card">
        <form onSubmit={handleMakeCall}>
          <div className="input-group">
            <label>Customer Name</label>
            <input 
              type="text" 
              className="input-field" 
              placeholder="e.g. Rahul Sharma"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="input-group">
            <label>Phone Number</label>
            <input 
              type="tel" 
              className="input-field" 
              placeholder="e.g. +919999999999"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </div>

          <div className="input-group">
            <label>AI Voice</label>
            <select 
              className="input-field" 
              value={voice}
              onChange={(e) => setVoice(e.target.value)}
              style={{ cursor: 'pointer' }}
            >
              <option value="Polly.Aditi">Aditi (Premium Female - Hindi/English)</option>
              <option value="Polly.Raveena">Raveena (Premium Female - Indian English)</option>
              <option value="man">Standard Male (Hindi/English)</option>
              <option value="woman">Standard Female (Hindi/English)</option>
            </select>
          </div>

          <div style={{ display: 'flex', gap: '1rem', width: '100%' }}>
            <button 
              type="button" 
              className="action-btn"
              onClick={handleTestCall}
              disabled={status === 'calling'}
              style={{ background: '#3f3f46', flex: 1 }}
            >
              🎧 Play Premium Online Preview
            </button>
            <button 
              type="submit" 
              className="action-btn"
              disabled={status === 'calling'}
              style={{ flex: 1 }}
            >
              🚀 Make Campaign Call
            </button>
          </div>
        </form>

        <div className="status-box">
          <div className={`status-dot ${status}`}></div>
          <span>{message}</span>
        </div>

        {status === 'calling' && (
          <div className="radar-container">
            <div className="radar"></div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
