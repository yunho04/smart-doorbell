package com.smartdoorbell.backend.mqtt.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import tools.jackson.databind.json.JsonMapper;

@Service
public class MqttPublisher {

    private static final Logger log = LoggerFactory.getLogger(MqttPublisher.class);

    private final MessageChannel mqttOutboundChannel;
    private final JsonMapper jsonMapper;

    public MqttPublisher(
            @Qualifier("mqttOutboundChannel") MessageChannel mqttOutboundChannel,
            JsonMapper jsonMapper
    ) {
        this.mqttOutboundChannel = mqttOutboundChannel;
        this.jsonMapper = jsonMapper;
    }

    public void publishAfterCommit(String topic, Object message) {
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                try {
                    publish(topic, jsonMapper.writeValueAsString(message));
                } catch (RuntimeException e) {
                    log.error("MQTT publish failed after commit for topic {}", topic, e);
                }
            }
        });
    }

    public void publish(String topic, String payload) {

        Message<String> message = MessageBuilder
                .withPayload(payload)
                .setHeader(MqttHeaders.TOPIC, topic)
                .setHeader(MqttHeaders.QOS, 1)
                .build();

        mqttOutboundChannel.send(message);
    }
}
