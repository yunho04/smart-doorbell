package com.smartdoorbell.backend.mqtt.config;

import com.smartdoorbell.backend.event.service.EventService;
import com.smartdoorbell.backend.mqtt.dto.SensorEventMessage;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessageProducer;
import org.springframework.integration.mqtt.core.DefaultMqttPahoClientFactory;
import org.springframework.integration.mqtt.core.MqttPahoClientFactory;
import org.springframework.integration.mqtt.inbound.MqttPahoMessageDrivenChannelAdapter;
import org.springframework.integration.mqtt.outbound.MqttPahoMessageHandler;
import org.springframework.integration.mqtt.support.DefaultPahoMessageConverter;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.json.JsonMapper;

@Configuration
@EnableIntegration
public class MqttConfig {

    private static final Logger log = LoggerFactory.getLogger(MqttConfig.class);

    @Value("${mqtt.broker-url}")
    private String brokerUrl;

    @Value("${mqtt.client-id}")
    private String clientId;

    @Value("${mqtt.topic}")
    private String topic;

    @Value("${mqtt.outbound-client-id}")
    private String outboundClientId;

    @Bean
    public MqttPahoClientFactory mqttClientFactory() {
        DefaultMqttPahoClientFactory factory =
                new DefaultMqttPahoClientFactory();

        MqttConnectOptions options = new MqttConnectOptions();

        options.setServerURIs(new String[]{brokerUrl});
        options.setAutomaticReconnect(true);
        options.setCleanSession(true);

        factory.setConnectionOptions(options);

        return factory;
    }

    @Bean
    public MessageChannel mqttInputChannel() {
        return new DirectChannel();
    }

    @Bean
    public MessageProducer mqttInbound(
            MqttPahoClientFactory mqttClientFactory
    ) {

        MqttPahoMessageDrivenChannelAdapter adapter =
                new MqttPahoMessageDrivenChannelAdapter(
                        clientId,
                        mqttClientFactory,
                        topic
                );

        adapter.setCompletionTimeout(5000);
        adapter.setConverter(new DefaultPahoMessageConverter());
        adapter.setQos(1);
        adapter.setOutputChannel(mqttInputChannel());

        return adapter;
    }
    @Bean
    @ServiceActivator(inputChannel = "mqttInputChannel")
    public MessageHandler mqttInboundHandler(JsonMapper jsonMapper, EventService eventService) {
        return message -> {
            String topic = message.getHeaders().get(MqttHeaders.RECEIVED_TOPIC, String.class);
            SensorEventMessage sensor;
            try {
                sensor = jsonMapper.readValue((String) message.getPayload(), SensorEventMessage.class);
            } catch (JacksonException e) {
                log.warn("Invalid sensor JSON on topic {}", topic);
                return;
            }

            if (sensor == null || sensor.deviceId() == null
                    || !("doorbell/" + sensor.deviceId() + "/sensor").equals(topic)) {
                log.warn("Invalid sensor device ID on topic {}", topic);
                return;
            }

            if (sensor.isPresenceDetected()) {
                try {
                    eventService.detectPresence(sensor.deviceId());
                } catch (IllegalArgumentException e) {
                    log.warn("Ignoring sensor message on topic {}: {}", topic, e.getMessage());
                }
            }
        };
    }

    @Bean
    public MessageChannel mqttOutboundChannel() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "mqttOutboundChannel")
    public MessageHandler mqttOutbound(
            MqttPahoClientFactory mqttClientFactory
    ) {
        MqttPahoMessageHandler handler =
                new MqttPahoMessageHandler(
                        outboundClientId,
                        mqttClientFactory
                );

        handler.setAsync(true);
        handler.setDefaultQos(1);

        return handler;
    }

}
