FROM maven:3.9.9-eclipse-temurin-21 AS build

WORKDIR /workspace
COPY frontend-javaweb/pom.xml ./pom.xml
RUN mvn -B -q dependency:go-offline
COPY frontend-javaweb/src ./src
RUN mvn -B -DskipTests package

FROM eclipse-temurin:21-jre-jammy

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /workspace/target/ppgl-analyze-0.0.1-SNAPSHOT.jar /app/app.jar

ENV PPGL_DATA_ROOT=/var/lib/ppgl-assist
EXPOSE 8080

HEALTHCHECK --interval=20s --timeout=5s --start-period=45s --retries=5 \
    CMD curl --fail --silent http://127.0.0.1:8080/ > /dev/null || exit 1

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
