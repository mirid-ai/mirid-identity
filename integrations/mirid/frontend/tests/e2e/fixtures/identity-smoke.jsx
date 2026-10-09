import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import IdentityPage from '../../../src/pages/IdentityPage';
import { applyServiceEndpoints } from '../../../src/config/api';
import '../../../src/App.css';

applyServiceEndpoints({ backend: 'http://127.0.0.1:8769', tts: 'http://127.0.0.1:8769' });

function IdentitySmoke() {
  const [visible, setVisible] = useState(true);
  return <main className="min-h-screen bg-background p-4 text-foreground">
    <button type="button" className="mb-4 text-sm" onClick={() => setVisible(false)}>Leave identity page</button>
    {visible ? <IdentityPage /> : <p>Identity page closed.</p>}
  </main>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><IdentitySmoke /></React.StrictMode>);
