
import React, { useEffect, useState } from 'react';
import { API_BASE_URL } from './apiConfig';

const SentEmails = () => {
    const [emails, setEmails] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetch(`${API_BASE_URL}/processed-records`)
            .then(res => res.json())
            .then(data => {
                setEmails(data);
                setLoading(false);
            })
            .catch(err => {
                console.error("Error fetching sent emails:", err);
                setLoading(false);
            });
    }, []);

    if (loading) return <div>Cargando historial de envíos...</div>;
    if (emails.length === 0) return null; // Don't show if empty

    return (
        <div style={{
            backgroundColor: '#f8f9fa',
            padding: '10px 20px',
            borderBottom: '1px solid #ddd',
            fontSize: '14px',
            marginBottom: '20px'
        }}>
            <h3 style={{ margin: '0 0 10px 0', fontSize: '16px', color: '#333' }}>
                📧 Últimos Correos Enviados Automáticamente
            </h3>
            <div style={{ maxHeight: '150px', overflowY: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ textAlign: 'left', borderBottom: '1px solid #ccc' }}>
                            <th style={{ padding: '5px' }}>Hoja</th>
                            <th style={{ padding: '5px' }}>ID Registro</th>
                            <th style={{ padding: '5px' }}>Enviado El</th>
                        </tr>
                    </thead>
                    <tbody>
                        {emails.map((email, index) => (
                            <tr key={index} style={{ borderBottom: '1px solid #eee' }}>
                                <td style={{ padding: '5px' }}>{email.sheet}</td>
                                <td style={{ padding: '5px' }}>{email.id}</td>
                                <td style={{ padding: '5px' }}>{new Date(email.enviado_el).toLocaleString()}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default SentEmails;
