
import React, { useEffect, useState } from 'react';
import { API_BASE_URL } from './apiConfig';

const SentEmails = ({ onBackToMenu }) => {
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

    return (
        <div style={{ padding: '20px' }}>
            <button
                onClick={onBackToMenu}
                style={{
                    marginBottom: '20px',
                    padding: '10px 20px',
                    backgroundColor: '#6c757d',
                    color: 'white',
                    border: 'none',
                    borderRadius: '5px',
                    cursor: 'pointer'
                }}
            >
                &larr; Volver al Menú
            </button>

            <div style={{
                backgroundColor: '#f8f9fa',
                padding: '20px',
                borderRadius: '8px',
                boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
            }}>
                <h3 style={{ margin: '0 0 20px 0', fontSize: '18px', color: '#333' }}>
                    📧 Historial de Correos Automáticos
                </h3>

                {loading ? (
                    <div>Cargando historial...</div>
                ) : emails.length === 0 ? (
                    <div>No hay correos enviados recientemente.</div>
                ) : (
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', backgroundColor: 'white' }}>
                            <thead>
                                <tr style={{ textAlign: 'left', borderBottom: '2px solid #ddd', backgroundColor: '#f1f1f1' }}>
                                    <th style={{ padding: '12px' }}>Hoja</th>
                                    <th style={{ padding: '12px' }}>ID Registro</th>
                                    <th style={{ padding: '12px' }}>Enviado El</th>
                                </tr>
                            </thead>
                            <tbody>
                                {emails.map((email, index) => (
                                    <tr key={index} style={{ borderBottom: '1px solid #eee' }}>
                                        <td style={{ padding: '10px' }}>{email.sheet}</td>
                                        <td style={{ padding: '10px' }}>{email.id}</td>
                                        <td style={{ padding: '10px' }}>{new Date(email.enviado_el).toLocaleString()}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
};

export default SentEmails;
