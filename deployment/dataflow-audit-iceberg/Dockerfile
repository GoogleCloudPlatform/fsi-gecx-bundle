FROM maven:3.9.14-eclipse-temurin-17 AS build
WORKDIR /workspace
COPY pom.xml .
RUN mvn -B dependency:go-offline
COPY src ./src
RUN mvn -B package dependency:copy-dependencies -DoutputDirectory=target/dependency

FROM gcr.io/dataflow-templates-base/java17-template-launcher-base:latest
COPY --from=build /workspace/target/audit-iceberg-dataflow-1.0.0.jar /template/classpath/
COPY --from=build /workspace/target/dependency/*.jar /template/classpath/
ENV FLEX_TEMPLATE_JAVA_MAIN_CLASS="com.google.cloud.fsi.audit.AuditIcebergPipeline"
ENV FLEX_TEMPLATE_JAVA_CLASSPATH="/template/classpath/*"
